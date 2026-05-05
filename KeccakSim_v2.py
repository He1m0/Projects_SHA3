"""KeccakSim_v2.py — Clean Keccak-f[1600] trace simulator.

Three leakage modes — all are sums of independently scaled components:

  hw    — hw_scale × HW(value) + hd_add_scale × HD(value, prev) + noise
  f9    — f9_scale × F9(value, t) + hd_add_scale × HD(value, prev) + noise
  mixed — hw_scale × HW(value) + f9_scale × F9(value, t)
          + hd_add_scale × HD(value, prev) + noise

  hw_scale / f9_scale default to 1.0/0.0 (hw) or 0.0/1.0 (f9) for backward
  compatibility. Pass --hw-scale / --f9-scale (or SIM_HW_SCALE / SIM_F9_SCALE)
  to override any combination.

F9 model (You & Kuhn 2022 / Schindler et al. 2005):
  F9(value, t) = Σ_{l} v[l]·C[t,l] + C[t,-1]
  Coefficients are pre-computed into a (T × n_coeffs) table and saved as a
  .npy file so the same table is reused across all simulation groups in a run.

Granularity:
  word — one 32-bit sample per leak() call  (n_coeffs = 33 for f9)
  byte — four 8-bit samples per leak() call (n_coeffs =  9 for f9)

Old simulator (KeccakSim_BI_TA.py) is kept unchanged for archive reproducibility.
"""

import numpy as np
import argparse
import sys
import csv
from pathlib import Path

DEBUG = False

# Precomputed 256×8 bit-decomposition matrix for byte-mode F9.
_BITS256 = np.array(
    [[(b >> i) & 1 for i in range(8)] for b in range(256)],
    dtype=np.float64,
)


# ---------------------------------------------------------------------------
# F9 table utilities
# ---------------------------------------------------------------------------

def generate_f9_table(table_size, granularity, f9_seed, c8_range):
    """Return a (table_size, n_coeffs) float64 array of F9 coefficients.

    n_coeffs = 9 (byte) or 33 (word).
    Columns 0..n-2 are bit coefficients drawn from U(0, 1).
    Column -1 is the per-position intercept drawn from U(-c8_range, +c8_range).
    """
    rng = np.random.default_rng(int(f9_seed))
    n_bits = 8 if granularity == "byte" else 32
    coeffs = rng.uniform(0.0, 1.0, size=(table_size, n_bits))
    intercepts = rng.uniform(-float(c8_range), float(c8_range), size=(table_size, 1))
    return np.concatenate([coeffs, intercepts], axis=1).astype(np.float64)


def load_or_generate_f9_table(path, table_size, granularity, f9_seed, c8_range):
    """Load table from *path* if it exists; otherwise generate and save it."""
    p = Path(path)
    n_coeffs = 9 if granularity == "byte" else 33
    if p.exists():
        table = np.load(p)
        if table.shape[0] < table_size or table.shape[1] != n_coeffs:
            raise ValueError(
                "Existing F9 table at '{}' has shape {} but need at least "
                "({}, {})".format(p, table.shape, table_size, n_coeffs)
            )
        return table
    table = generate_f9_table(table_size, granularity, f9_seed, c8_range)
    p.parent.mkdir(parents=True, exist_ok=True)
    np.save(p, table)
    return table


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class KeccakTraceSimulator:

    str2num = {'0': 0, '1': 1, '2': 2, '3': 3,
               '4': 4, '5': 5, '6': 6, '7': 7,
               '8': 8, '9': 9, 'a':10, 'b':11,
               'c':12, 'd':13, 'e':14, 'f':15}

    KeccakRoundConstants = [
        [0x00000001, 0x00000000], [0x00000000, 0x00000089],
        [0x00000000, 0x8000008B], [0x00000000, 0x80008080],
        [0x00000001, 0x0000008B], [0x00000001, 0x00008000],
        [0x00000001, 0x80008088], [0x00000001, 0x80000082],
        [0x00000000, 0x0000000B], [0x00000000, 0x0000000A],
        [0x00000001, 0x00008082], [0x00000000, 0x00008003],
        [0x00000001, 0x0000808B], [0x00000001, 0x8000000B],
        [0x00000001, 0x8000008A], [0x00000001, 0x80000081],
        [0x00000000, 0x80000081], [0x00000000, 0x80000008],
        [0x00000000, 0x00000083], [0x00000000, 0x80008003],
        [0x00000001, 0x80008088], [0x00000000, 0x80000088],
        [0x00000001, 0x00008000], [0x00000000, 0x80008082],
    ]

    RhoOffsets = [0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39,
                  41, 45, 15, 21, 8, 18, 2, 61, 56, 14]

    # All leakage points are active (equivalent to leakage_profile="full").
    leak_bit_interleaving  = True
    leak_memory_moves      = True
    leak_permutation_moves = True
    leak_init              = True

    def __init__(
        self,
        mode="hw",
        granularity="byte",
        noise_sigma=0.0,
        hd_add_scale=0.0,
        hw_scale=None,
        f9_scale=None,
        rng_seed=None,
        f9_table=None,
    ):
        if mode not in ("hw", "f9", "mixed"):
            raise ValueError("mode must be 'hw', 'f9', or 'mixed' (got '{}')".format(mode))
        if granularity not in ("word", "byte"):
            raise ValueError("granularity must be 'word' or 'byte' (got '{}')".format(granularity))
        self.mode = mode
        self.granularity = granularity
        self.noise_sigma = float(noise_sigma)
        self.hd_add_scale = float(hd_add_scale)
        # Derive per-component scales from mode when not explicitly provided.
        if mode == "f9":
            self.hw_scale = 0.0 if hw_scale is None else float(hw_scale)
            self.f9_scale = 1.0 if f9_scale is None else float(f9_scale)
        elif mode == "mixed":
            self.hw_scale = 1.0 if hw_scale is None else float(hw_scale)
            self.f9_scale = 1.0 if f9_scale is None else float(f9_scale)
        else:  # hw
            self.hw_scale = 1.0 if hw_scale is None else float(hw_scale)
            self.f9_scale = 0.0 if f9_scale is None else float(f9_scale)
        self.f9_table = f9_table  # ndarray (T, 9) or (T, 33), or None
        self.rng = np.random.default_rng(rng_seed)
        self.trace = []
        self.invocation_trace_ranges = []
        self.sample_index = 0
        self.invocation_sample_index = 0
        self._hd_prev_word = 0
        self._hd_prev_bytes = [0, 0, 0, 0]

    # ------------------------------------------------------------------
    # Trace lifecycle
    # ------------------------------------------------------------------

    def reset(self):
        self.trace = []
        self.invocation_trace_ranges = []
        self.sample_index = 0
        self.invocation_sample_index = 0
        self._hd_prev_word = 0
        self._hd_prev_bytes = [0, 0, 0, 0]

    def _finalize_trace(self):
        pass  # trace is already a plain list of floats

    def get_invocation_traces(self):
        return [self.trace[s:e] for s, e in self.invocation_trace_ranges]

    def write_trace_values_to_file(self, trace_values, file_path, separator="\n",
                                   append=False, trace_format="text", trace_dtype="int16"):
        trace_path = Path(file_path)
        if trace_path.parent:
            trace_path.parent.mkdir(parents=True, exist_ok=True)
        if trace_format == "text":
            mode = "a" if append else "w"
            text = separator.join(str(v) for v in trace_values)
            with trace_path.open(mode, encoding="utf-8") as f:
                if append and trace_path.exists() and trace_path.stat().st_size > 0 and separator:
                    f.write(separator)
                f.write(text)
        elif trace_format == "bin":
            arr = np.asarray(trace_values, dtype=np.dtype(trace_dtype))
            with trace_path.open("ab" if append else "wb") as f:
                arr.tofile(f)
        else:
            raise ValueError("Unsupported trace format: {}".format(trace_format))
        return str(trace_path)

    def write_trace_to_file(self, file_path, separator="\n", append=False,
                            trace_format="text", trace_dtype="int16"):
        return self.write_trace_values_to_file(
            self.trace, file_path,
            separator=separator, append=append,
            trace_format=trace_format, trace_dtype=trace_dtype,
        )

    # ------------------------------------------------------------------
    # Leakage primitives
    # ------------------------------------------------------------------

    def get_hw(self, value):
        return bin(int(value) & 0xFFFFFFFF).count('1')

    def _emit(self, signal):
        n = float(self.rng.normal(0.0, self.noise_sigma)) if self.noise_sigma > 0 else 0.0
        self.trace.append(signal + n)
        self.sample_index += 1
        self.invocation_sample_index += 1

    def _leak_signal(self, value):
        # signal = hw_scale*HW + f9_scale*F9 + hd_add_scale*HD
        # Use invocation_sample_index for F9 so all permutation invocations share
        # the same per-position coefficients (modular over the table size).
        if self.granularity == "byte":
            cur = [((value >> s) & 0xFF) for s in (0, 8, 16, 24)]
            for i, b in enumerate(cur):
                sig = 0.0
                if self.hw_scale:
                    sig += self.hw_scale * bin(b).count("1")
                if self.f9_scale:
                    if self.f9_table is None:
                        raise RuntimeError(
                            "f9_scale > 0 requires a pre-computed coefficient table. "
                            "Pass f9_table= to __init__ or use --f9-table on the CLI."
                        )
                    row = self.f9_table[self.invocation_sample_index % len(self.f9_table)]
                    sig += self.f9_scale * (float(_BITS256[b] @ row[:8]) + row[8])
                hd = self.hd_add_scale * bin(b ^ self._hd_prev_bytes[i]).count("1") if self.hd_add_scale else 0.0
                self._emit(sig + hd)
            self._hd_prev_bytes = cur
        else:
            sig = 0.0
            if self.hw_scale:
                sig += self.hw_scale * bin(value).count("1")
            if self.f9_scale:
                if self.f9_table is None:
                    raise RuntimeError(
                        "f9_scale > 0 requires a pre-computed coefficient table. "
                        "Pass f9_table= to __init__ or use --f9-table on the CLI."
                    )
                row = self.f9_table[self.invocation_sample_index % len(self.f9_table)]
                bits = np.array([(value >> l) & 1 for l in range(32)], dtype=np.float64)
                sig += self.f9_scale * (float(np.dot(bits, row[:32])) + row[32])
            hd = self.hd_add_scale * bin(value ^ self._hd_prev_word).count("1") if self.hd_add_scale else 0.0
            self._emit(sig + hd)
            self._hd_prev_word = value

    def leak(self, value):
        value = int(value) & 0xFFFFFFFF
        self._leak_signal(value)
        return value

    # ------------------------------------------------------------------
    # Leaky 32-bit logic primitives
    # ------------------------------------------------------------------

    def leak_xor(self, a, b):
        a, b = int(a), int(b)
        res = self.leak(a ^ b)
        if DEBUG and res != (a ^ b): print("Error in leak_xor!")
        return res

    def leak_not(self, a):
        a = int(a)
        res = self.leak((~a) & 0xFFFFFFFF)
        if DEBUG and res != (~a & 0xFFFFFFFF): print("Error in leak_not!")
        return res

    def leak_and(self, a, b):
        a, b = int(a), int(b)
        res = self.leak(a & b)
        if DEBUG and res != (a & b): print("Error in leak_and!")
        return res

    def leak_ROL32(self, a, offset):
        if offset != 0:
            a = int(a)
            res = self.leak_xor(self.leak(a << offset) & 0xFFFFFFFF,
                                self.leak(a >> (32 - offset)) & 0xFFFFFFFF)
        else:
            res = self.leak(a)
        if DEBUG and res != self.ROL32(a, offset): print("Error in leak_ROL32!")
        return res

    def leak_ROL64(self, even_in, odd_in, offset):
        even_in, odd_in = int(even_in), int(odd_in)
        offset = offset & 63
        if offset % 2 == 0:
            even_out = self.leak_ROL32(even_in, offset // 2)
            odd_out  = self.leak_ROL32(odd_in,  offset // 2)
        else:
            even_out = self.leak_ROL32(odd_in,  (offset + 1) // 2)
            odd_out  = self.leak_ROL32(even_in, (offset - 1) // 2)
        if DEBUG:
            ec, oc = self.ROL64(even_in, odd_in, offset)
            if even_out != ec or odd_out != oc: print("Error in leak_ROL64!")
        return even_out, odd_out

    def ROL32(self, a, offset):
        offset = offset & 63
        return ((a << offset) & 0xFFFFFFFF) ^ (a >> (32 - offset)) if offset else a

    def ROL64(self, even_in, odd_in, offset):
        even_in, odd_in = int(even_in), int(odd_in)
        offset = offset & 63
        if offset % 2 == 0:
            return self.ROL32(even_in, offset // 2), self.ROL32(odd_in, offset // 2)
        return self.ROL32(odd_in, (offset + 1) // 2), self.ROL32(even_in, (offset - 1) // 2)

    # ------------------------------------------------------------------
    # Bit interleaving
    # ------------------------------------------------------------------

    def toBitInterleaving(self, laneLow, laneHigh):
        laneLow, laneHigh = int(laneLow), int(laneHigh)
        even = odd = 0
        for i in range(64):
            bit = (laneLow >> i) & 1 if i < 32 else (laneHigh >> (i - 32)) & 1
            if i % 2 == 0: even |= bit << (i // 2)
            else:           odd  |= bit << ((i - 1) // 2)
        return even, odd

    def leak_toBitInterleaving(self, laneLow, laneHigh):
        if not self.leak_bit_interleaving:
            return self.toBitInterleaving(laneLow, laneHigh)
        laneLow, laneHigh = int(laneLow), int(laneHigh)
        even = odd = 0
        for i in range(64):
            bit = self.leak((laneLow >> i) & 1) if i < 32 else self.leak((laneHigh >> (i - 32)) & 1)
            if i % 2 == 0: even |= self.leak(bit << (i // 2))
            else:           odd  |= self.leak(bit << ((i - 1) // 2))
        return even, odd

    def fromBitInterleaving(self, even_in, odd_in):
        even_in, odd_in = int(even_in), int(odd_in)
        laneLow = laneHigh = 0
        for i in range(64):
            bit = (even_in >> (i // 2)) & 1 if i % 2 == 0 else (odd_in >> ((i - 1) // 2)) & 1
            if i < 32: laneLow  |= bit << i
            else:      laneHigh |= bit << (i - 32)
        return laneLow, laneHigh

    def leak_fromBitInterleaving(self, even_in, odd_in):
        if not self.leak_bit_interleaving:
            return self.fromBitInterleaving(even_in, odd_in)
        even_in, odd_in = int(even_in), int(odd_in)
        laneLow = laneHigh = 0
        for i in range(64):
            bit = self.leak((even_in >> (i // 2)) & 1) if i % 2 == 0 else self.leak((odd_in >> ((i - 1) // 2)) & 1)
            if i < 32: laneLow  |= self.leak(bit << i)
            else:      laneHigh |= self.leak(bit << (i - 32))
        return laneLow, laneHigh

    def index(self, x, y, z):
        return ((x % 5) + 5 * (y % 5)) * 2 + z

    def _ensure_writable_buffer(self, buf, name):
        if not isinstance(buf, (np.ndarray, bytearray, list)):
            raise TypeError("{} must be a writable buffer".format(name))

    # ------------------------------------------------------------------
    # Keccak permutation steps
    # ------------------------------------------------------------------

    def theta(self, State):
        C = np.zeros((5, 2), dtype=np.uint32)
        D = np.zeros((5, 2), dtype=np.uint32)
        for x in range(5):
            for z in range(2):
                for y in range(5):
                    C[x][z] ^= State[self.index(x, y, z)]
        for x in range(5):
            D[x][0], D[x][1] = self.ROL64(C[(x+1)%5][0], C[(x+1)%5][1], 1)
            for z in range(2):
                D[x][z] ^= C[(x+4)%5][z]
        for x in range(5):
            for y in range(5):
                for z in range(2):
                    State[self.index(x, y, z)] ^= D[x][z]

    def leak_theta(self, State):
        sc = np.array(State, dtype=np.uint32, copy=True) if DEBUG else None
        C = np.zeros((5, 2), dtype=np.uint32)
        D = np.zeros((5, 2), dtype=np.uint32)
        for x in range(5):
            for z in range(2):
                for y in range(5):
                    C[x][z] = self.leak_xor(C[x][z], State[self.index(x, y, z)])
        for x in range(5):
            D[x][0], D[x][1] = self.leak_ROL64(C[(x+1)%5][0], C[(x+1)%5][1], 1)
            for z in range(2):
                D[x][z] = self.leak_xor(D[x][z], C[(x+4)%5][z])
        for x in range(5):
            for y in range(5):
                for z in range(2):
                    State[self.index(x, y, z)] = self.leak_xor(State[self.index(x, y, z)], D[x][z])
        if DEBUG:
            self.theta(sc)
            if not np.array_equal(np.array(State, dtype=np.uint32), sc):
                print("Error in leak_theta!")

    def rho(self, State):
        for x in range(5):
            for y in range(5):
                State[self.index(x, y, 0)], State[self.index(x, y, 1)] = \
                    self.ROL64(State[self.index(x, y, 0)], State[self.index(x, y, 1)], self.RhoOffsets[x+5*y])

    def leak_rho(self, State):
        sc = np.array(State, dtype=np.uint32, copy=True) if DEBUG else None
        for x in range(5):
            for y in range(5):
                State[self.index(x, y, 0)], State[self.index(x, y, 1)] = \
                    self.leak_ROL64(State[self.index(x, y, 0)], State[self.index(x, y, 1)], self.RhoOffsets[x+5*y])
        if DEBUG:
            self.rho(sc)
            if not np.array_equal(np.array(State, dtype=np.uint32), sc):
                print("Error in leak_rho!")

    def pi(self, State):
        tmp = np.zeros(50, dtype=np.uint32)
        for x in range(5):
            for y in range(5):
                for z in range(2):
                    tmp[self.index(x, y, z)] = State[self.index(x, y, z)]
        for x in range(5):
            for y in range(5):
                for z in range(2):
                    State[self.index(x*0+y*1, x*2+y*3, z)] = tmp[self.index(x, y, z)]

    def leak_pi(self, State):
        if not self.leak_permutation_moves:
            self.pi(State)
            return
        sc = np.array(State, dtype=np.uint32, copy=True) if DEBUG else None
        tmp = np.zeros(50, dtype=np.uint32)
        for x in range(5):
            for y in range(5):
                for z in range(2):
                    tmp[self.index(x, y, z)] = self.leak(State[self.index(x, y, z)])
        for x in range(5):
            for y in range(5):
                for z in range(2):
                    State[self.index(x*0+y*1, x*2+y*3, z)] = self.leak(tmp[self.index(x, y, z)])
        if DEBUG:
            self.pi(sc)
            if not np.array_equal(np.array(State, dtype=np.uint32), sc):
                print("Error in leak_pi!")

    def chi(self, State):
        C = np.zeros((5, 2), dtype=np.uint32)
        for y in range(5):
            for x in range(5):
                for z in range(2):
                    C[x][z] = State[self.index(x, y, z)] ^ ((~State[self.index(x+1, y, z)]) & State[self.index(x+2, y, z)])
            for x in range(5):
                for z in range(2):
                    State[self.index(x, y, z)] = C[x][z]

    def leak_chi(self, State):
        sc = np.array(State, dtype=np.uint32, copy=True) if DEBUG else None
        C = np.zeros((5, 2), dtype=np.uint32)
        for y in range(5):
            for x in range(5):
                for z in range(2):
                    C[x][z] = self.leak_xor(State[self.index(x, y, z)],
                                            self.leak_and(self.leak_not(State[self.index(x+1, y, z)]),
                                                          State[self.index(x+2, y, z)]))
            for x in range(5):
                for z in range(2):
                    State[self.index(x, y, z)] = self.leak(C[x][z])
        if DEBUG:
            self.chi(sc)
            if not np.array_equal(np.array(State, dtype=np.uint32), sc):
                print("Error in leak_chi!")

    def iota(self, State, round_idx):
        State[self.index(0, 0, 0)] ^= self.KeccakRoundConstants[round_idx][0]
        State[self.index(0, 0, 1)] ^= self.KeccakRoundConstants[round_idx][1]

    def leak_iota(self, State, round_idx):
        sc = np.array(State, dtype=np.uint32, copy=True) if DEBUG else None
        State[self.index(0, 0, 0)] = self.leak_xor(State[self.index(0, 0, 0)], self.KeccakRoundConstants[round_idx][0])
        State[self.index(0, 0, 1)] = self.leak_xor(State[self.index(0, 0, 1)], self.KeccakRoundConstants[round_idx][1])
        if DEBUG:
            self.iota(sc, round_idx)
            if not np.array_equal(np.array(State, dtype=np.uint32), sc):
                print("Error in leak_iota!")

    # ------------------------------------------------------------------
    # Sponge construction
    # ------------------------------------------------------------------

    def KeccakP1600_AddBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            for i in range(length): laneAsBytes[offset + i] = data[dataOffset + i]
            LOW  = int(laneAsBytes[0]) | (int(laneAsBytes[1])<<8) | (int(laneAsBytes[2])<<16) | (int(laneAsBytes[3])<<24)
            HIGH = int(laneAsBytes[4]) | (int(laneAsBytes[5])<<8) | (int(laneAsBytes[6])<<16) | (int(laneAsBytes[7])<<24)
            lane = np.zeros(2, dtype=np.uint32)
            lane[0], lane[1] = self.toBitInterleaving(LOW, HIGH)
            State[lanePosition*2] ^= lane[0]
            State[lanePosition*2+1] ^= lane[1]

    def leak_KeccakP1600_AddBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        if not self.leak_memory_moves:
            self.KeccakP1600_AddBytesInLane(State, lanePosition, data, dataOffset, offset, length)
            return
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            for i in range(length): laneAsBytes[offset + i] = self.leak(data[dataOffset + i])
            LOW  = self.leak(int(laneAsBytes[0]) | (int(laneAsBytes[1])<<8) | (int(laneAsBytes[2])<<16) | (int(laneAsBytes[3])<<24))
            HIGH = self.leak(int(laneAsBytes[4]) | (int(laneAsBytes[5])<<8) | (int(laneAsBytes[6])<<16) | (int(laneAsBytes[7])<<24))
            lane = np.zeros(2, dtype=np.uint32)
            lane[0], lane[1] = self.leak_toBitInterleaving(LOW, HIGH)
            State[lanePosition*2]   = self.leak_xor(State[lanePosition*2],   lane[0])
            State[lanePosition*2+1] = self.leak_xor(State[lanePosition*2+1], lane[1])

    def _add_bytes_loop(self, State, data, offset, length, dataOffset, leaky):
        lp, ofl = offset // 8, offset % 8
        fn = self.leak_KeccakP1600_AddBytesInLane if leaky else self.KeccakP1600_AddBytesInLane
        while length > 0:
            bil = min(8 - ofl, length)
            fn(State, lp, data, dataOffset, ofl, bil)
            length -= bil; lp += 1; ofl = 0; dataOffset += bil

    def KeccakP1600_AddBytes(self, State, data, offset, length, dataOffset=0):
        self._add_bytes_loop(State, data, offset, length, dataOffset, False)

    def leak_KeccakP1600_AddBytes(self, State, data, offset, length, dataOffset=0):
        self._add_bytes_loop(State, data, offset, length, dataOffset, True)

    def KeccakP1600_ExtractBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            lane = np.zeros(2, dtype=np.uint32)
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            lane[0], lane[1] = self.fromBitInterleaving(State[lanePosition*2], State[lanePosition*2+1])
            for idx, shift in enumerate([0, 8, 16, 24]):
                laneAsBytes[idx]   = (lane[0] >> shift) & 0xFF
                laneAsBytes[idx+4] = (lane[1] >> shift) & 0xFF
            for i in range(length): data[dataOffset + i] = laneAsBytes[offset + i]

    def leak_KeccakP1600_ExtractBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        if not self.leak_memory_moves:
            self.KeccakP1600_ExtractBytesInLane(State, lanePosition, data, dataOffset, offset, length)
            return
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            lane = np.zeros(2, dtype=np.uint32)
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            lane[0], lane[1] = self.leak_fromBitInterleaving(State[lanePosition*2], State[lanePosition*2+1])
            for idx, shift in enumerate([0, 8, 16, 24]):
                laneAsBytes[idx]   = (lane[0] >> shift) & 0xFF
                laneAsBytes[idx+4] = (lane[1] >> shift) & 0xFF
            for i in range(length): data[dataOffset + i] = self.leak(laneAsBytes[offset + i])

    def _extract_bytes_loop(self, State, data, offset, length, dataOffset, leaky):
        self._ensure_writable_buffer(data, "data")
        lp, ofl = offset // 8, offset % 8
        fn = self.leak_KeccakP1600_ExtractBytesInLane if leaky else self.KeccakP1600_ExtractBytesInLane
        while length > 0:
            bil = min(8 - ofl, length)
            fn(State, lp, data, dataOffset, ofl, bil)
            length -= bil; lp += 1; ofl = 0; dataOffset += bil

    def KeccakP1600_ExtractBytes(self, State, data, offset, length, dataOffset=0):
        self._extract_bytes_loop(State, data, offset, length, dataOffset, False)

    def leak_KeccakP1600_ExtractBytes(self, State, data, offset, length, dataOffset=0):
        self._extract_bytes_loop(State, data, offset, length, dataOffset, True)

    def KeccakP1600_ExtractAndAddBytesInLane(self, State, lanePosition, input, inputOffset,
                                              output, outputOffset, offset, length):
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            tmp = np.zeros(8, dtype=np.uint8)
            self.KeccakP1600_ExtractBytesInLane(State, lanePosition, tmp, 0, offset, length)
            for i in range(length): output[outputOffset+i] = input[inputOffset+i] ^ tmp[i]

    def leak_KeccakP1600_ExtractAndAddBytesInLane(self, State, lanePosition, input, inputOffset,
                                                   output, outputOffset, offset, length):
        if not self.leak_memory_moves:
            self.KeccakP1600_ExtractAndAddBytesInLane(State, lanePosition, input, inputOffset,
                                                       output, outputOffset, offset, length)
            return
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            tmp = np.zeros(8, dtype=np.uint8)
            self.leak_KeccakP1600_ExtractBytesInLane(State, lanePosition, tmp, 0, offset, length)
            for i in range(length): output[outputOffset+i] = self.leak(input[inputOffset+i] ^ tmp[i])

    def _extract_add_loop(self, State, input, output, offset, length, inputOffset, outputOffset, leaky):
        self._ensure_writable_buffer(output, "output")
        lp, ofl = offset // 8, offset % 8
        fn = self.leak_KeccakP1600_ExtractAndAddBytesInLane if leaky else self.KeccakP1600_ExtractAndAddBytesInLane
        while length > 0:
            bil = min(8 - ofl, length)
            fn(State, lp, input, inputOffset, output, outputOffset, ofl, bil)
            length -= bil; lp += 1; ofl = 0; inputOffset += bil; outputOffset += bil

    def KeccakP1600_ExtractAndAddBytes(self, State, input, output, offset, length, inputOffset=0, outputOffset=0):
        self._extract_add_loop(State, input, output, offset, length, inputOffset, outputOffset, False)

    def leak_KeccakP1600_ExtractAndAddBytes(self, State, input, output, offset, length, inputOffset=0, outputOffset=0):
        self._extract_add_loop(State, input, output, offset, length, inputOffset, outputOffset, True)

    def KeccakP1600_OverwriteBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            self.KeccakP1600_ExtractBytesInLane(State, lanePosition, laneAsBytes, 0, 0, 8)
            for i in range(length): laneAsBytes[offset+i] = data[dataOffset+i]
            LOW  = int(laneAsBytes[0]) | (int(laneAsBytes[1])<<8) | (int(laneAsBytes[2])<<16) | (int(laneAsBytes[3])<<24)
            HIGH = int(laneAsBytes[4]) | (int(laneAsBytes[5])<<8) | (int(laneAsBytes[6])<<16) | (int(laneAsBytes[7])<<24)
            lane = np.zeros(2, dtype=np.uint32)
            lane[0], lane[1] = self.toBitInterleaving(LOW, HIGH)
            State[lanePosition*2] = lane[0]; State[lanePosition*2+1] = lane[1]

    def leak_KeccakP1600_OverwriteBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        if not self.leak_memory_moves:
            self.KeccakP1600_OverwriteBytesInLane(State, lanePosition, data, dataOffset, offset, length)
            return
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            self.leak_KeccakP1600_ExtractBytesInLane(State, lanePosition, laneAsBytes, 0, 0, 8)
            for i in range(length): laneAsBytes[offset+i] = self.leak(data[dataOffset+i])
            LOW  = self.leak(int(laneAsBytes[0]) | (int(laneAsBytes[1])<<8) | (int(laneAsBytes[2])<<16) | (int(laneAsBytes[3])<<24))
            HIGH = self.leak(int(laneAsBytes[4]) | (int(laneAsBytes[5])<<8) | (int(laneAsBytes[6])<<16) | (int(laneAsBytes[7])<<24))
            lane = np.zeros(2, dtype=np.uint32)
            lane[0], lane[1] = self.leak_toBitInterleaving(LOW, HIGH)
            State[lanePosition*2] = self.leak(lane[0]); State[lanePosition*2+1] = self.leak(lane[1])

    def _overwrite_bytes_loop(self, State, data, offset, length, dataOffset, leaky):
        lp, ofl = offset // 8, offset % 8
        fn = self.leak_KeccakP1600_OverwriteBytesInLane if leaky else self.KeccakP1600_OverwriteBytesInLane
        while length > 0:
            bil = min(8 - ofl, length)
            fn(State, lp, data, dataOffset, ofl, bil)
            length -= bil; lp += 1; ofl = 0; dataOffset += bil

    def KeccakP1600_OverwriteBytes(self, State, data, offset, length, dataOffset=0):
        self._overwrite_bytes_loop(State, data, offset, length, dataOffset, False)

    def leak_KeccakP1600_OverwriteBytes(self, State, data, offset, length, dataOffset=0):
        self._overwrite_bytes_loop(State, data, offset, length, dataOffset, True)

    def KeccakP1600_OverwriteWithZeroes(self, State, byteCount):
        laneAsBytes = np.zeros(8, dtype=np.uint8)
        lp = 0
        while byteCount > 0:
            if byteCount < 8:
                self.KeccakP1600_OverwriteBytesInLane(State, lp, laneAsBytes, 0, 0, byteCount)
                byteCount = 0
            else:
                State[lp*2] = State[lp*2+1] = 0
                byteCount -= 8; lp += 1

    def leak_KeccakP1600_OverwriteWithZeroes(self, State, byteCount):
        if not self.leak_memory_moves:
            self.KeccakP1600_OverwriteWithZeroes(State, byteCount)
            return
        laneAsBytes = np.zeros(8, dtype=np.uint8)
        lp = 0
        while byteCount > 0:
            if byteCount < 8:
                self.leak_KeccakP1600_OverwriteBytesInLane(State, lp, laneAsBytes, 0, 0, byteCount)
                byteCount = 0
            else:
                State[lp*2] = self.leak(0); State[lp*2+1] = self.leak(0)
                byteCount -= 8; lp += 1

    def KeccakP1600_PermutationOnWords(self, State, rounds):
        for i in range(24 - rounds, 24):
            self.theta(State); self.rho(State); self.pi(State); self.chi(State); self.iota(State, i)

    def KeccakP1600_leak_PermutationOnWords(self, State, rounds):
        self.invocation_sample_index = 0
        start = len(self.trace)
        for i in range(24 - rounds, 24):
            self.leak_theta(State); self.leak_rho(State)
            self.leak_pi(State); self.leak_chi(State); self.leak_iota(State, i)
        self.invocation_trace_ranges.append((start, len(self.trace)))

    def KeccakP1600_Permute_24rounds(self, State):
        self.KeccakP1600_PermutationOnWords(State, 24)

    def KeccakP1600_Permute_Nrounds(self, State, rounds):
        self.KeccakP1600_PermutationOnWords(State, rounds)

    def KeccakP1600_Initialize(self, State):
        for i in range(50): State[i] = 0

    def leak_KeccakP1600_Initialize(self, State):
        if not self.leak_init:
            self.KeccakP1600_Initialize(State)
            return
        for i in range(50): State[i] = self.leak(0)

    def _sponge_init(self, rate, capacity, leaky):
        if rate + capacity != 1600 or rate <= 0 or rate >= 1600 or rate % 8 != 0:
            print("Error in SpongeInitialize: invalid rate/capacity")
            return 1
        self.State = np.zeros(50, dtype=np.uint32)
        if leaky: self.leak_KeccakP1600_Initialize(self.State)
        else:     self.KeccakP1600_Initialize(self.State)
        self.rate = rate; self.byteIOIndex = 0; self.squeezing = False
        return 0

    def SpongeInitialize(self, rate, capacity):      return self._sponge_init(rate, capacity, False)
    def leak_SpongeInitialize(self, rate, capacity): return self._sponge_init(rate, capacity, True)

    def SpongeAbsorb(self, data, dataByteLen):
        if self.squeezing: print("Error: absorb after squeezing"); return 1
        rateB = self.rate // 8; cur = 0; i = 0
        while i < dataByteLen:
            if self.byteIOIndex == 0 and dataByteLen - i >= rateB:
                while dataByteLen - i >= rateB:
                    self.KeccakP1600_AddBytes(self.State, data, 0, rateB, cur)
                    self.KeccakP1600_PermutationOnWords(self.State, 24)
                    cur += rateB; i += rateB
            else:
                pb = min(rateB - self.byteIOIndex, dataByteLen - i)
                i += pb
                self.KeccakP1600_AddBytes(self.State, data, self.byteIOIndex, pb, cur)
                self.byteIOIndex += pb; cur += pb
                if self.byteIOIndex == rateB:
                    self.KeccakP1600_PermutationOnWords(self.State, 24); self.byteIOIndex = 0
        return 0

    def leak_SpongeAbsorb(self, data, dataByteLen):
        if self.squeezing: print("Error: absorb after squeezing"); return 1
        rateB = self.rate // 8; cur = 0; i = 0
        while i < dataByteLen:
            if self.byteIOIndex == 0 and dataByteLen - i >= rateB:
                while dataByteLen - i >= rateB:
                    self.leak_KeccakP1600_AddBytes(self.State, data, 0, rateB, cur)
                    self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
                    cur += rateB; i += rateB
            else:
                pb = min(rateB - self.byteIOIndex, dataByteLen - i)
                i += pb
                self.leak_KeccakP1600_AddBytes(self.State, data, self.byteIOIndex, pb, cur)
                self.byteIOIndex += pb; cur += pb
                if self.byteIOIndex == rateB:
                    self.KeccakP1600_leak_PermutationOnWords(self.State, 24); self.byteIOIndex = 0
        return 0

    def SpongeAbsorbLastFewBits(self, delimitedData):
        if not delimitedData or self.squeezing: return 1
        rateB = self.rate // 8
        self.KeccakP1600_AddBytes(self.State, [delimitedData], self.byteIOIndex, 1)
        if delimitedData >= 0x80 and self.byteIOIndex == rateB - 1:
            self.KeccakP1600_PermutationOnWords(self.State, 24)
        self.KeccakP1600_AddBytes(self.State, [0x80], rateB - 1, 1)
        self.KeccakP1600_PermutationOnWords(self.State, 24)
        self.byteIOIndex = 0; self.squeezing = True
        return 0

    def leak_SpongeAbsorbLastFewBits(self, delimitedData):
        if not delimitedData or self.squeezing: return 1
        rateB = self.rate // 8
        self.leak_KeccakP1600_AddBytes(self.State, [delimitedData], self.byteIOIndex, 1)
        if delimitedData >= 0x80 and self.byteIOIndex == rateB - 1:
            self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
        self.leak_KeccakP1600_AddBytes(self.State, [0x80], rateB - 1, 1)
        self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
        self.byteIOIndex = 0; self.squeezing = True
        return 0

    def SpongeSqueeze(self, data, dataByteLen):
        if not self.squeezing:
            if self.SpongeAbsorbLastFewBits(0x01) != 0: return 1
        rateB = self.rate // 8; i = 0; cur = 0
        while i < dataByteLen:
            if self.byteIOIndex == rateB and dataByteLen - i >= rateB:
                for j in range(dataByteLen - i, rateB, -rateB):
                    self.KeccakP1600_PermutationOnWords(self.State, 24)
                    self.KeccakP1600_ExtractBytes(self.State, data, 0, rateB, cur)
                    cur += rateB
                i = dataByteLen - j
            else:
                if self.byteIOIndex == rateB:
                    self.KeccakP1600_PermutationOnWords(self.State, 24); self.byteIOIndex = 0
                pb = min(rateB - self.byteIOIndex, dataByteLen - i)
                i += pb
                self.KeccakP1600_ExtractBytes(self.State, data, self.byteIOIndex, pb, cur)
                cur += pb; self.byteIOIndex += pb
        return 0

    def leak_SpongeSqueeze(self, data, dataByteLen):
        if not self.squeezing:
            if self.leak_SpongeAbsorbLastFewBits(0x01) != 0: return 1
        rateB = self.rate // 8; i = 0; cur = 0
        while i < dataByteLen:
            if self.byteIOIndex == rateB and dataByteLen - i >= rateB:
                for j in range(dataByteLen - i, rateB, -rateB):
                    self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
                    self.leak_KeccakP1600_ExtractBytes(self.State, data, 0, rateB, cur)
                    cur += rateB
                i = dataByteLen - j
            else:
                if self.byteIOIndex == rateB:
                    self.KeccakP1600_leak_PermutationOnWords(self.State, 24); self.byteIOIndex = 0
                pb = min(rateB - self.byteIOIndex, dataByteLen - i)
                i += pb
                self.leak_KeccakP1600_ExtractBytes(self.State, data, self.byteIOIndex, pb, cur)
                cur += pb; self.byteIOIndex += pb
        return 0

    # ------------------------------------------------------------------
    # SHA3 / SHAKE
    # ------------------------------------------------------------------

    def _sha3(self, d, M, leaky):
        cap = 2 * d; rate = 1600 - cap
        init = self.leak_SpongeInitialize if leaky else self.SpongeInitialize
        absorb = self.leak_SpongeAbsorb if leaky else self.SpongeAbsorb
        last = self.leak_SpongeAbsorbLastFewBits if leaky else self.SpongeAbsorbLastFewBits
        squeeze = self.leak_SpongeSqueeze if leaky else self.SpongeSqueeze
        if init(rate, cap) != 0: return "XX"
        buf = np.frombuffer(bytes.fromhex(M), dtype=np.uint8)
        if absorb(buf, len(buf)) != 0: return "XX"
        if last(0x06) != 0: return "XX"
        out = np.zeros(d // 8, dtype=np.uint8)
        if squeeze(out, d // 8) != 0: return "XX"
        return bytes(out).hex()

    def _shake(self, s, M, d, leaky):
        if d % 8 != 0: return "XX"
        cap = 2 * s; rate = 1600 - cap
        init = self.leak_SpongeInitialize if leaky else self.SpongeInitialize
        absorb = self.leak_SpongeAbsorb if leaky else self.SpongeAbsorb
        last = self.leak_SpongeAbsorbLastFewBits if leaky else self.SpongeAbsorbLastFewBits
        squeeze = self.leak_SpongeSqueeze if leaky else self.SpongeSqueeze
        if init(rate, cap) != 0: return "XX"
        buf = np.frombuffer(bytes.fromhex(M), dtype=np.uint8)
        if absorb(buf, len(buf)) != 0: return "XX"
        if last(0x1F) != 0: return "XX"
        out = np.zeros(d // 8, dtype=np.uint8)
        if squeeze(out, d // 8) != 0: return "XX"
        return bytes(out).hex()

    def SHA3_224(self, M): return self._sha3(224, M, False)
    def SHA3_256(self, M): return self._sha3(256, M, False)
    def SHA3_384(self, M): return self._sha3(384, M, False)
    def SHA3_512(self, M): return self._sha3(512, M, False)
    def SHAKE128(self, M, B): return self._shake(128, M, B * 8, False)
    def SHAKE256(self, M, B): return self._shake(256, M, B * 8, False)

    def _generate_trace(self, algo, M, output_file=None, separator="\n",
                        append=False, trace_format="text", trace_dtype="int16"):
        self.reset()
        self._sha3(*{"sha3-224": (224,), "sha3-256": (256,), "sha3-384": (384,), "sha3-512": (512,)}[algo], M, True)
        self._finalize_trace()
        if output_file is not None:
            self.write_trace_to_file(output_file, separator=separator, append=append,
                                     trace_format=trace_format, trace_dtype=trace_dtype)
        return self.trace

    def generate_trace_SHA3_224(self, M, **kw): return self._generate_trace("sha3-224", M, **kw)
    def generate_trace_SHA3_256(self, M, **kw): return self._generate_trace("sha3-256", M, **kw)
    def generate_trace_SHA3_384(self, M, **kw): return self._generate_trace("sha3-384", M, **kw)
    def generate_trace_SHA3_512(self, M, **kw): return self._generate_trace("sha3-512", M, **kw)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_cli_parser():
    p = argparse.ArgumentParser(description="KeccakSim v2 — HW / F9 leakage models")
    p.add_argument("--algorithm", choices=["sha3-224","sha3-256","sha3-384","sha3-512","shake128","shake256"])
    p.add_argument("--input-hex")
    p.add_argument("--input-text")
    p.add_argument("--bytes", type=int, default=32)
    p.add_argument("--trace", action="store_true")
    p.add_argument("--trace-file")
    p.add_argument("--trace-format", choices=["text","bin"], default="text")
    p.add_argument("--trace-dtype", default="int16")
    p.add_argument("--trace-separator", default="\n")
    p.add_argument("--append-trace", action="store_true")
    # Leakage model
    p.add_argument("--mode", choices=["hw","f9","mixed"], default="hw",
                   help="Leakage model: hw, f9, or mixed (default: hw). "
                        "In mixed mode all three components are active; use "
                        "--hw-scale/--f9-scale/--hd-add-scale to weight them.")
    p.add_argument("--granularity", choices=["word","byte"], default="byte",
                   help="Emission granularity: word (1 sample/leak) or byte (4 samples/leak, default)")
    p.add_argument("--noise-sigma", type=float, default=0.0,
                   help="Std-dev of additive Gaussian noise per sample (default: 0)")
    p.add_argument("--hw-scale", type=float, default=None,
                   help="HW component scale (default: 1.0 for hw/mixed, 0.0 for f9)")
    p.add_argument("--f9-scale", type=float, default=None,
                   help="F9 component scale (default: 1.0 for f9/mixed, 0.0 for hw)")
    p.add_argument("--hd-add-scale", type=float, default=0.0,
                   help="HD component scale added on top of hw+f9 (default: 0 = disabled)")
    # F9 table
    p.add_argument("--f9-table",
                   help="Path to F9 coefficient table .npy. If missing, generate+save it.")
    p.add_argument("--f9-table-size", type=int, default=None,
                   help="Number of rows in the F9 table (= max sample index + 1). "
                        "Required only when creating a new table.")
    p.add_argument("--f9-seed", type=int, default=2839,
                   help="RNG seed for F9 table generation (default: 2839)")
    p.add_argument("--f9-c8-range", type=float, default=0.5,
                   help="Half-width of U(-r,+r) for F9 intercept column (default: 0.5)")
    p.add_argument("--generate-f9-table", action="store_true",
                   help="Generate and save F9 table then exit (requires --f9-table and --f9-table-size)")
    # RNG
    p.add_argument("--bulk-seed", type=int, default=None,
                   help="RNG seed for bulk input generation and noise (default: random)")
    # Bulk
    p.add_argument("--bulk-invocations", type=int, default=None)
    p.add_argument("--bulk-folders", type=int, default=None)
    p.add_argument("--bulk-traces-per-folder", type=int, default=None)
    p.add_argument("--random-input-bytes", type=int, default=32)
    p.add_argument("--bulk-output-dir", default="bulk_traces")
    p.add_argument("--bulk-index-file", default=None)
    p.add_argument("--bulk-index-dir", default=None)
    p.add_argument("--bulk-data-format", choices=["uint8","hex"], default="hex")
    # Deprecated / ignored (accepted silently for env-file compatibility)
    for _flag in ["--bulk-count","--bulk-total-traces"]:
        p.add_argument(_flag, type=int, default=0)
    return p


def _rate_in_bytes_for_sha3_algorithm(algo):
    return {
        "sha3-224": (1600 - 448) // 8,
        "sha3-256": (1600 - 512) // 8,
        "sha3-384": (1600 - 768) // 8,
        "sha3-512": (1600 - 1024) // 8,
    }[algo]


def _derive_random_input_bytes_for_invocations(algo, invocations):
    if invocations <= 0: raise ValueError("bulk-invocations must be > 0")
    rate = _rate_in_bytes_for_sha3_algorithm(algo)
    return 1 if invocations == 1 else (invocations - 1) * rate


def _run_single(sim, algo, message_hex, args, trace_output_file=None):
    trace = None
    if algo in ("sha3-224","sha3-256","sha3-384","sha3-512"):
        if args.trace:
            gen = getattr(sim, "generate_trace_{}".format(algo.replace("-","_").upper()))
            trace = gen(
                message_hex,
                output_file=trace_output_file,
                separator=args.trace_separator,
                append=args.append_trace,
                trace_format=args.trace_format,
                trace_dtype=args.trace_dtype,
            )
        digest = getattr(sim, algo.replace("-","_").upper())(message_hex)
    elif algo == "shake128":
        digest = sim.SHAKE128(message_hex, args.bytes)
    elif algo == "shake256":
        digest = sim.SHAKE256(message_hex, args.bytes)
    else:
        raise ValueError("Unsupported algorithm: {}".format(algo))
    return digest, trace


def main():
    parser = _build_cli_parser()
    args = parser.parse_args()

    # --generate-f9-table mode: create table and exit.
    if args.generate_f9_table:
        if not args.f9_table:
            parser.error("--generate-f9-table requires --f9-table PATH")
        if not args.f9_table_size:
            parser.error("--generate-f9-table requires --f9-table-size N")
        table = generate_f9_table(args.f9_table_size, args.granularity, args.f9_seed, args.f9_c8_range)
        p = Path(args.f9_table)
        p.parent.mkdir(parents=True, exist_ok=True)
        np.save(p, table)
        print("f9_table_saved={}".format(p))
        print("f9_table_shape={}x{}".format(*table.shape))
        return 0

    if args.algorithm is None:
        parser.error("--algorithm is required")

    algo = args.algorithm

    if args.trace and algo in ("shake128","shake256"):
        parser.error("Trace generation is implemented only for SHA3 algorithms")

    # Resolve F9 table — needed whenever the effective f9_scale will be non-zero.
    _f9_scale_effective = args.f9_scale if args.f9_scale is not None else (
        1.0 if args.mode in ("f9", "mixed") else 0.0
    )
    f9_table = None
    if _f9_scale_effective > 0:
        if not args.f9_table:
            parser.error("--mode {} with f9_scale > 0 requires --f9-table PATH".format(args.mode))
        table_size = args.f9_table_size
        if not Path(args.f9_table).exists():
            if not table_size:
                parser.error(
                    "F9 table '{}' does not exist; provide --f9-table-size to create it".format(args.f9_table)
                )
        f9_table = load_or_generate_f9_table(
            args.f9_table, table_size or 1, args.granularity, args.f9_seed, args.f9_c8_range
        )

    sim = KeccakTraceSimulator(
        mode=args.mode,
        granularity=args.granularity,
        noise_sigma=args.noise_sigma,
        hd_add_scale=args.hd_add_scale,
        hw_scale=args.hw_scale,
        f9_scale=args.f9_scale,
        rng_seed=args.bulk_seed,
        f9_table=f9_table,
    )

    bulk_mode = args.bulk_folders is not None or args.bulk_traces_per_folder is not None

    if bulk_mode:
        if not args.trace:
            parser.error("Bulk mode requires --trace")
        if algo in ("shake128","shake256"):
            parser.error("Bulk mode is implemented only for SHA3 algorithms")
        if args.input_hex is not None or args.input_text is not None:
            parser.error("Do not provide --input-hex/--input-text in bulk mode")
        if args.bulk_folders is None or args.bulk_traces_per_folder is None:
            parser.error("Bulk mode requires both --bulk-folders and --bulk-traces-per-folder")

        n_folders = args.bulk_folders
        tpf = args.bulk_traces_per_folder
        total = n_folders * tpf

        in_bytes = args.random_input_bytes
        if args.bulk_invocations is not None:
            try: in_bytes = _derive_random_input_bytes_for_invocations(algo, args.bulk_invocations)
            except ValueError as e: parser.error(str(e))

        rng = np.random.default_rng(args.bulk_seed)
        base = Path(args.bulk_output_dir)
        index_dir = Path(args.bulk_index_dir) if args.bulk_index_dir else None
        if index_dir: index_dir.mkdir(parents=True, exist_ok=True)

        summaries = []
        global_sample = 0
        for fi in range(n_folders):
            folder = Path("{}{}".format(args.bulk_output_dir, fi).format(fi))
            folder = Path("{}{:04d}".format(args.bulk_output_dir, fi))
            folder.mkdir(parents=True, exist_ok=True)
            index_path = (Path(args.bulk_index_file) if args.bulk_index_file and n_folders == 1
                          else (index_dir / "index_{:04d}.csv".format(fi) if index_dir
                                else folder / ".index.csv"))
            data_in_path = folder / "data_in.npy"
            data_out_path = folder / "data_out.npy"
            data_in_rows, data_out_rows = [], []

            with index_path.open("w", newline="", encoding="utf-8") as idx_f:
                w = csv.writer(idx_f)
                w.writerow(["sample","global_sample","input_hex","digest","trace_files",
                             "invocation_trace_lens","trace_len_total","invocation_count"])
                for si in range(tpf):
                    msg_bytes = rng.integers(0, 256, size=in_bytes, dtype=np.uint8).tobytes()
                    msg_hex = msg_bytes.hex()
                    digest, trace = _run_single(sim, algo, msg_hex, args)
                    inv_traces = sim.get_invocation_traces()
                    inv_files, inv_lens = [], []
                    sfx = "bin" if args.trace_format == "bin" else "txt"
                    for inv_i, inv_t in enumerate(inv_traces):
                        tp = folder / "trace_{:04d}_{}_ch0.{}".format(si, inv_i, sfx)
                        sim.write_trace_values_to_file(inv_t, tp, separator=args.trace_separator,
                                                       trace_format=args.trace_format, trace_dtype=args.trace_dtype)
                        inv_files.append(str(tp)); inv_lens.append(len(inv_t))
                    if args.bulk_invocations and len(inv_traces) != args.bulk_invocations:
                        parser.error("bulk-invocations mismatch: expected {} got {}".format(
                            args.bulk_invocations, len(inv_traces)))
                    if args.bulk_data_format == "hex":
                        data_in_rows.append(msg_hex); data_out_rows.append(digest)
                    else:
                        data_in_rows.append(np.frombuffer(msg_bytes, dtype=np.uint8).copy())
                        data_out_rows.append(np.frombuffer(bytes.fromhex(digest), dtype=np.uint8).copy())
                    w.writerow([si, global_sample, msg_hex, digest, ";".join(inv_files),
                                 ";".join(str(v) for v in inv_lens), len(trace), len(inv_traces)])
                    global_sample += 1

            if args.bulk_data_format == "hex":
                np.save(data_in_path,  np.asarray(data_in_rows,  dtype=str))
                np.save(data_out_path, np.asarray(data_out_rows, dtype=str))
            else:
                np.save(data_in_path,  np.asarray(data_in_rows,  dtype=np.uint8) if data_in_rows
                        else np.zeros((0, in_bytes), dtype=np.uint8))
                dig_bytes = {"sha3-224":28,"sha3-256":32,"sha3-384":48,"sha3-512":64}[algo]
                np.save(data_out_path, np.asarray(data_out_rows, dtype=np.uint8) if data_out_rows
                        else np.zeros((0, dig_bytes), dtype=np.uint8))
            summaries.append((folder, index_path, data_in_path, data_out_path, tpf))

        print("bulk_samples={}".format(total))
        print("total_traces_generated={}".format(total))
        print("bulk_output_base={}".format(base))
        print("bulk_folders={}".format(n_folders))
        print("bulk_traces_per_folder={}".format(tpf))
        print("bulk_random_input_bytes={}".format(in_bytes))
        print("bulk_data_format={}".format(args.bulk_data_format))
        for folder, ip, dip, dop, count in summaries:
            print("folder={}".format(folder))
            print("folder_samples={}".format(count))
            print("bulk_index_file={}".format(ip))
            print("bulk_data_in_file={}".format(dip))
            print("bulk_data_out_file={}".format(dop))
        return 0

    # Single-trace mode.
    if args.input_hex is not None and args.input_text is not None:
        parser.error("Use only one of --input-hex or --input-text")
    if args.input_text is not None:
        message_hex = args.input_text.encode("utf-8").hex()
    elif args.input_hex is not None:
        try: bytes.fromhex(args.input_hex)
        except ValueError as e: parser.error("Invalid hex input: {}".format(e))
        message_hex = args.input_hex
    else:
        parser.error("One of --input-hex or --input-text is required")

    digest, trace = _run_single(sim, algo, message_hex, args, trace_output_file=args.trace_file)
    print(digest)
    if args.trace:
        print("trace_len={}".format(len(trace)))
        if args.trace_file: print("trace_file={}".format(args.trace_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
