import numpy as np
import binascii
import argparse
import sys
import csv
from pathlib import Path

# This is an adapted version of KeccakSim2.py, which is a simple Keccak-f[1600] permutation simulator that generates 
# Hamming Weight traces for the internal state. The main difference is that this version does not just split up the 64-bit lanes
# into LOW and HIGH 32-bit parts, but it adapts the Bit Interleaving as implemented in https://github.com/XKCP/XKCP/blob/master/lib/low/KeccakP-1600/ref-32bits/KeccakP-1600-reference32BI.c

# Example command to bulk generate traces for template building:
# python3 KeccakSim_BI_TA.py --algorithm sha3-512 --trace --bulk-invocations 10 --bulk-traces-per-folder 16 --bulk-folders 2 --bulk-output-dir traces/Raw_TR/Raw_TR_ --bulk-index-dir traces/RAW_TR_indexes --trace-format bin --trace-dtype float64

DEBUG = False

class KeccakTraceSimulator:
    # --- Class Constants ---

    str2num = {'0': 0, '1': 1, '2': 2, '3': 3,\
            '4': 4, '5': 5, '6': 6, '7': 7,\
            '8': 8, '9': 9, 'a':10, 'b':11,\
            'c':12, 'd':13, 'e':14, 'f':15 }

    #Round constants for Keccak-f[1600]
    KeccakRoundConstants = [
        [0x00000001, 0x00000000],
        [0x00000000, 0x00000089],
        [0x00000000, 0x8000008B],
        [0x00000000, 0x80008080],
        [0x00000001, 0x0000008B],
        [0x00000001, 0x00008000],
        [0x00000001, 0x80008088],
        [0x00000001, 0x80000082],
        [0x00000000, 0x0000000B],
        [0x00000000, 0x0000000A],
        [0x00000001, 0x00008082],
        [0x00000000, 0x00008003],
        [0x00000001, 0x0000808B],
        [0x00000001, 0x8000000B],
        [0x00000001, 0x8000008A],
        [0x00000001, 0x80000081],
        [0x00000000, 0x80000081],
        [0x00000000, 0x80000008],
        [0x00000000, 0x00000083],
        [0x00000000, 0x80008003],
        [0x00000001, 0x80008088],
        [0x00000000, 0x80000088],
        [0x00000001, 0x00008000],
        [0x00000000, 0x80008082]
    ]


    RhoOffsets = [0,  1, 62, 28, 27, 36, 44,  6, 55, 20,  3, 10, 43, 25, 39, 41, 45, 15, 21,  8, 18,  2, 61, 56, 14]

    # --- Class Functions ---

    def __init__(
        self,
        noise_level=0,
        noise_sigma=0.0,
        gain_jitter_sigma=0.0,
        offset_jitter_sigma=0.0,
        smooth_window=1,
        hw_scale=1.0,
        common_wave_scale=0.0,
        common_wave_period=256,
        common_wave_scope="trace",
        hw_ratio=None,
        leakage_profile="full",
        leakage_granularity="word",
        rng_seed=None,
        seed_pbw=None,
        pbw_shared=False,
        pbw_c8_range=0.5,
    ):
        """Constructor for KeccakTraceSimulator with optional realism controls."""
        self.trace = []
        self.invocation_trace_ranges = []
        self.noise = float(noise_level)
        self.noise_sigma = float(noise_sigma)
        self.gain_jitter_sigma = float(gain_jitter_sigma)
        self.offset_jitter_sigma = float(offset_jitter_sigma)
        self.smooth_window = max(1, int(smooth_window))
        # Backward-compatible mode: explicit scales.
        self.hw_scale = float(hw_scale)
        self.common_wave_scale = float(common_wave_scale)
        # Optional single-knob mode: relative contribution ratio.
        self.hw_ratio = None
        if hw_ratio is not None:
            self.hw_ratio = min(max(float(hw_ratio), 0.0), 1.0)
            self.hw_scale = self.hw_ratio
            self.common_wave_scale = 1.0 - self.hw_ratio
        self.common_wave_period = max(1, int(common_wave_period))
        self.common_wave_scope = str(common_wave_scope).strip().lower()
        if self.common_wave_scope not in ("trace", "invocation"):
            raise ValueError("Unsupported common_wave_scope: {}".format(common_wave_scope))
        self.leakage_profile = str(leakage_profile).strip().lower()
        if self.leakage_profile == "full":
            self.leak_bit_interleaving = True
            self.leak_memory_moves = True
            self.leak_permutation_moves = True
            self.leak_init = True
        elif self.leakage_profile in ("focused", "logic-only"):
            self.leak_bit_interleaving = False
            self.leak_memory_moves = False
            self.leak_permutation_moves = False
            self.leak_init = False
        else:
            raise ValueError("Unsupported leakage_profile: {}".format(leakage_profile))
        self.leakage_granularity = str(leakage_granularity).strip().lower()
        if self.leakage_granularity not in (
            "word", "byte", "byte-bitweighted", "word-bitweighted",
        ):
            raise ValueError("Unsupported leakage_granularity: {}".format(leakage_granularity))
        # Stochastic-model templates (the F_9 model in You & Kuhn 2022,
        # Sect. 2.1; originally Schindler/Lemke/Paar 2005) build per-byte
        # expected traces as
        #     x_b(t) = c_8(t) + Σ_{l=0..7} b[l] · c_l(t),  c_l, c_8 ∈ ℝ^m
        # i.e. each bit-coefficient AND the intercept is a vector of length
        # m (one entry per sample point). Templates trained on real silicon
        # implicitly recover this per-position structure.
        #
        # Two simulator modes:
        #
        #   pbw_shared = False (default, F_9-faithful):
        #     For each leakage point t we lazily draw 9 independent
        #     coefficients (c_0..c_7 ~ U(0,1) and c_8 ~ U(-c8_range, +c8_range))
        #     from the seeded `pbw_rng`. Bytes are emitted via a per-position
        #     256-entry LUT; words via per-position (32 weights, 1 intercept)
        #     tuples. This is the canonical "per-leakage-point pbw" form
        #     (advisor's LUT proposal) and matches what the templates fit.
        #
        #   pbw_shared = True (legacy, pre-Apr-29 behaviour):
        #     A single 8-vector and a single 32-vector drawn once at init are
        #     reused at every leakage point. Equivalent to enforcing
        #     c_l(t) = c_l(t') for all t — a *collapsed* F_9. Kept solely
        #     for reproducing pre-rework archives (smoke widerpbw / strict /
        #     realnoise / paperscale_*) byte-identically.
        self.pbw_shared = bool(pbw_shared)
        self.pbw_c8_range = float(pbw_c8_range)
        if self.pbw_c8_range < 0:
            raise ValueError("pbw_c8_range must be >= 0 (got {})".format(pbw_c8_range))
        self.pbw_rng = np.random.default_rng(0xB17 if seed_pbw is None else int(seed_pbw))
        self.seed_pbw = 0xB17 if seed_pbw is None else int(seed_pbw)
        # Legacy shared 8/32-vector + half-sums. Always drawn first so that
        # pbw_shared=True reproduces pre-rework leakage byte-identical given
        # the same seed_pbw.
        self._pbw_byte = self.pbw_rng.uniform(0.0, 1.0, size=8)
        self._pbw_word = self.pbw_rng.uniform(0.0, 1.0, size=32)
        self._pbw_byte_half = float(self._pbw_byte.sum()) * 0.5
        self._pbw_word_half = float(self._pbw_word.sum()) * 0.5
        # F_9 per-leakage-point storage. Lazily populated on first
        # encounter of each sample_index. _bits256 is the 256×8 byte→bit
        # decomposition matrix (rows in (b[0], b[1], ..., b[7]) order to
        # match _emit_sample_pbw's bit indexing).
        self._bits256 = np.array(
            [[(b >> i) & 1 for i in range(8)] for b in range(256)],
            dtype=np.float64,
        )
        self._pbw_byte_lut = []                  # list[ndarray (256,)]
        self._pbw_word_weights_per_pos = []      # list[ndarray (32,)]
        self._pbw_word_half_per_pos = []         # list[float]
        self._pbw_word_intercept_per_pos = []    # list[float]
        self.rng = np.random.default_rng(rng_seed)
        self.trace_gain = 1.0
        self.trace_offset = 0.0
        self.sample_index = 0
        self.invocation_sample_index = 0
        self._resample_trace_transform()

    def _resample_trace_transform(self):
        """Sample per-trace analog-like gain/offset perturbations."""
        if self.gain_jitter_sigma > 0:
            self.trace_gain = 1.0 + float(self.rng.normal(0.0, self.gain_jitter_sigma))
        else:
            self.trace_gain = 1.0
        if self.offset_jitter_sigma > 0:
            self.trace_offset = float(self.rng.normal(0.0, self.offset_jitter_sigma))
        else:
            self.trace_offset = 0.0

    def _finalize_trace(self):
        """Apply per-trace transformations after all leakage samples are generated."""
        if not self.trace:
            return
        arr = np.asarray(self.trace, dtype=np.float64)
        if self.smooth_window > 1:
            kernel = np.ones(self.smooth_window, dtype=np.float64) / float(self.smooth_window)
            arr = np.convolve(arr, kernel, mode="same")
        arr = arr * self.trace_gain + self.trace_offset
        self.trace = arr.tolist()

    def reset(self):
        """Resets the trace to an empty list."""
        self.trace = []
        self.invocation_trace_ranges = []
        self.sample_index = 0
        self.invocation_sample_index = 0
        self._resample_trace_transform()

    def write_trace_values_to_file(self, trace_values, file_path, separator="\n", append=False, trace_format="text", trace_dtype="int16"):
        """Write arbitrary trace values to a file and return the written path."""
        trace_path = Path(file_path)
        if trace_path.parent:
            trace_path.parent.mkdir(parents=True, exist_ok=True)

        if trace_format == "text":
            mode = "a" if append else "w"
            trace_as_text = separator.join(str(v) for v in trace_values)
            with trace_path.open(mode, encoding="utf-8") as out_file:
                if append and trace_path.exists() and trace_path.stat().st_size > 0 and separator:
                    out_file.write(separator)
                out_file.write(trace_as_text)
        elif trace_format == "bin":
            dtype = np.dtype(trace_dtype)
            trace_array = np.asarray(trace_values, dtype=dtype)
            mode = "ab" if append else "wb"
            with trace_path.open(mode) as out_file:
                trace_array.tofile(out_file)
        else:
            raise ValueError(f"Unsupported trace format: {trace_format}")

        return str(trace_path)

    def write_trace_to_file(self, file_path, separator="\n", append=False, trace_format="text", trace_dtype="int16"):
        """Write the current trace to a file and return the written path."""
        return self.write_trace_values_to_file(
            self.trace,
            file_path,
            separator=separator,
            append=append,
            trace_format=trace_format,
            trace_dtype=trace_dtype,
        )

    def get_invocation_traces(self):
        """Return leakage trace chunks, one per Keccak permutation invocation."""
        return [self.trace[start:end] for start, end in self.invocation_trace_ranges]

    # --- Leakage Simulation Primitives ---

    def get_hw(self, value):
        """Function to compute Hamming Weight of a 32-bit value."""
        value = int(value)
        return bin(value & 0xFFFFFFFF).count('1')

    def get_noise(self):
        """Get additive noise sample for one leakage observation."""
        if self.noise_sigma > 0:
            return self.noise + float(self.rng.normal(0.0, self.noise_sigma))
        return self.noise
    
    def _emit_sample(self, hw, center):
        """Emit one leakage sample with the given centered Hamming-weight contribution."""
        sample_value = center + self.hw_scale * (float(hw) - center)
        if self.common_wave_scale != 0.0:
            wave_index = self.sample_index
            if self.common_wave_scope == "invocation":
                wave_index = self.invocation_sample_index
            phase = (2.0 * np.pi * float(wave_index)) / float(self.common_wave_period)
            sample_value += self.common_wave_scale * (np.sin(phase) + 0.35 * np.sin((3.0 * phase) + 0.4))
        sample_value += self.get_noise()
        self.trace.append(sample_value)
        self.sample_index += 1
        self.invocation_sample_index += 1

    def _emit_sample_pbw(self, value, weights, w_sum_half, center):
        """Emit one leakage sample as Σ wᵢ·bitᵢ — collapsed-F_9 path
        (pbw_shared=True). Uses a single shared `weights` vector for all
        sample positions."""
        v = int(value)
        n = weights.shape[0]
        weighted = 0.0
        for i in range(n):
            if (v >> i) & 1:
                weighted += weights[i]
        sample_value = center + self.hw_scale * (weighted - w_sum_half)
        if self.common_wave_scale != 0.0:
            wave_index = self.sample_index
            if self.common_wave_scope == "invocation":
                wave_index = self.invocation_sample_index
            phase = (2.0 * np.pi * float(wave_index)) / float(self.common_wave_period)
            sample_value += self.common_wave_scale * (np.sin(phase) + 0.35 * np.sin((3.0 * phase) + 0.4))
        sample_value += self.get_noise()
        self.trace.append(sample_value)
        self.sample_index += 1
        self.invocation_sample_index += 1

    def _pbw_byte_lut_at(self, idx):
        """Return the (256,) per-byte centered contribution at sample
        position `idx`. Lazily extends the table from `pbw_rng` when a new
        position is encountered. Each entry is
            lut[b] = c_8(t) + Σᵢ (b[i] − ½)·c_l[i](t)
        so that E_b[lut[b]] = c_8(t) (per-position baseline), and
        var_b[lut[b]] picks up only the bit-coefficient variation."""
        while len(self._pbw_byte_lut) <= idx:
            c_l = self.pbw_rng.uniform(0.0, 1.0, size=8)
            c_8 = float(self.pbw_rng.uniform(-self.pbw_c8_range, self.pbw_c8_range))
            # bits256 @ c_l = Σᵢ b[i]·c_l[i]; subtract ½·Σ c_l to mean-center
            # the bit signal, then add c_8 as the per-position baseline.
            lut = self._bits256 @ c_l - 0.5 * float(c_l.sum()) + c_8
            self._pbw_byte_lut.append(lut)
        return self._pbw_byte_lut[idx]

    def _pbw_word_at(self, idx):
        """Return (weights, w_sum_half, c_8) for word leakage at sample
        position `idx`, lazily extending from `pbw_rng`."""
        while len(self._pbw_word_weights_per_pos) <= idx:
            c_l = self.pbw_rng.uniform(0.0, 1.0, size=32)
            c_8 = float(self.pbw_rng.uniform(-self.pbw_c8_range, self.pbw_c8_range))
            self._pbw_word_weights_per_pos.append(c_l)
            self._pbw_word_half_per_pos.append(float(c_l.sum()) * 0.5)
            self._pbw_word_intercept_per_pos.append(c_8)
        return (self._pbw_word_weights_per_pos[idx],
                self._pbw_word_half_per_pos[idx],
                self._pbw_word_intercept_per_pos[idx])

    def _emit_sample_byte_lut(self, byte_value, center):
        """Emit one byte-bitweighted sample via the per-position LUT
        (F_9-faithful path, pbw_shared=False)."""
        contrib = self._pbw_byte_lut_at(self.sample_index)[int(byte_value) & 0xFF]
        sample_value = center + self.hw_scale * float(contrib)
        if self.common_wave_scale != 0.0:
            wave_index = self.sample_index
            if self.common_wave_scope == "invocation":
                wave_index = self.invocation_sample_index
            phase = (2.0 * np.pi * float(wave_index)) / float(self.common_wave_period)
            sample_value += self.common_wave_scale * (np.sin(phase) + 0.35 * np.sin((3.0 * phase) + 0.4))
        sample_value += self.get_noise()
        self.trace.append(sample_value)
        self.sample_index += 1
        self.invocation_sample_index += 1

    def _emit_sample_word_pbw(self, value, center):
        """Emit one word-bitweighted sample with per-position weights +
        intercept (F_9-faithful path, pbw_shared=False)."""
        weights, w_sum_half, c_8 = self._pbw_word_at(self.sample_index)
        v = int(value) & 0xFFFFFFFF
        weighted = 0.0
        for i in range(32):
            if (v >> i) & 1:
                weighted += weights[i]
        sample_value = center + self.hw_scale * (weighted - w_sum_half + c_8)
        if self.common_wave_scale != 0.0:
            wave_index = self.sample_index
            if self.common_wave_scope == "invocation":
                wave_index = self.invocation_sample_index
            phase = (2.0 * np.pi * float(wave_index)) / float(self.common_wave_period)
            sample_value += self.common_wave_scale * (np.sin(phase) + 0.35 * np.sin((3.0 * phase) + 0.4))
        sample_value += self.get_noise()
        self.trace.append(sample_value)
        self.sample_index += 1
        self.invocation_sample_index += 1

    def leak(self, value):
        """Simulate leakage of a 32-bit value. Sample count and shape depend on leakage_granularity:
          - 'word'              : 1 HW(uint32) sample
          - 'byte'              : 4 HW(byte) samples
          - 'word-bitweighted'  : 1 Σwᵢ·bitᵢ sample over 32 bits
          - 'byte-bitweighted'  : 4 Σwᵢ·bitᵢ samples over 8 bits each
        """
        value = int(value) & 0xFFFFFFFF
        g = self.leakage_granularity
        if g == "byte":
            for shift in (0, 8, 16, 24):
                byte_hw = bin((value >> shift) & 0xFF).count("1")
                self._emit_sample(byte_hw, 4.0)
        elif g == "byte-bitweighted":
            for shift in (0, 8, 16, 24):
                byte = (value >> shift) & 0xFF
                if self.pbw_shared:
                    self._emit_sample_pbw(byte,
                                          self._pbw_byte, self._pbw_byte_half, 4.0)
                else:
                    self._emit_sample_byte_lut(byte, 4.0)
        elif g == "word-bitweighted":
            if self.pbw_shared:
                self._emit_sample_pbw(value,
                                      self._pbw_word, self._pbw_word_half, 16.0)
            else:
                self._emit_sample_word_pbw(value, 16.0)
        else:  # "word"
            self._emit_sample(self.get_hw(value), 16.0)
        return value

    # --- leaky 32-bit Logic Primitives ---
    # We work on 32-bit even or odd parts of the 64-bit lanes so we need primitive 32-bit operations.
    # Only rotate works on "full 64-bit" lanes, but still uses interleaved representation.

    def leak_xor(self, a, b):
        """Function to simulate leakage of XOR operation between two 32-bit values. Computes the XOR, simulates leakage, and checks for correctness."""
        a = int(a)
        b = int(b)
        res = self.leak(a ^ b)
        if DEBUG:
            if (res != (a ^ b)):
                print("Error in leak_xor!")
        return res
    
    def leak_not(self, a):
        """Function to simulate leakage of NOT operation on a 32-bit value. Computes the NOT, simulates leakage, and checks for correctness."""
        a = int(a)
        res = self.leak((~a) & 0xFFFFFFFF)
        if DEBUG:
            if (res != (~a & 0xFFFFFFFF)):
                print("Error in leak_not!")
        return res  

    def leak_and(self, a, b):
        """Function to simulate leakage of AND operation between two 32-bit values. Computes the AND, simulates leakage, and checks for correctness."""
        a = int(a)
        b = int(b)
        res = self.leak(a & b)
        if DEBUG:
            if (res != (a & b)):
                print("Error in leak_and!")
        return res

    def leak_ROL32(self, a, offset):
        """Function to simulate leakage of rotation operation on a 32-bit value. Computes the rotation, simulates leakage, and checks for correctness."""
        if offset != 0:
            a = int(a)
            res = self.leak_xor(self.leak(a << offset) & 0xFFFFFFFF, self.leak(a >> (32 - offset)) & 0xFFFFFFFF)
        else:
            res = self.leak(a)
        if DEBUG:
            if (res != self.ROL32(a, offset)):
                print("Error in leak_ROL32!")
        return res

    def leak_ROL64(self, even_in, odd_in, offset):
        """Function to simulate leakage of rotation operation on a 64-bit value represented in interleaved form. Computes the rotation, simulates leakage, and checks for correctness."""
        even_in = int(even_in)
        odd_in = int(odd_in)
        offset = offset & (2**6 - 1)
        if offset % 2 == 0:
            even_out = self.leak_ROL32(even_in, offset//2)
            odd_out = self.leak_ROL32(odd_in, offset//2)
        else:
            even_out = self.leak_ROL32(odd_in, (offset+1)//2)
            odd_out = self.leak_ROL32(even_in, (offset-1)//2)
        if DEBUG:
            even_out_check, odd_out_check = self.ROL64(even_in, odd_in, offset)
            if (even_out != even_out_check) or (odd_out != odd_out_check):
                print("Error in leak_ROL64!")
        return even_out, odd_out
    
    # Non-leaky version of ROL64 for verification
    def ROL32(self, a, offset):
        """Function to perform rotation operation on a 32-bit value."""
        offset = offset & (2**6 - 1)
        if offset != 0:
            res = ((a << offset) & 0xFFFFFFFF) ^ (a >> (32 - offset))
        else:
            res = a
        return res

    def ROL64(self, even_in, odd_in, offset):
        """Function to perform rotation operation on a 64-bit value represented in interleaved form."""
        even_in = int(even_in)
        odd_in = int(odd_in)
        offset = offset & (2**6 - 1)
        if offset % 2 == 0:
            even_out = self.ROL32(even_in, offset//2)
            odd_out = self.ROL32(odd_in, offset//2)
        else:
            even_out = self.ROL32(odd_in, (offset+1)//2)
            odd_out = self.ROL32(even_in, (offset-1)//2)
        return even_out, odd_out

    # Bit Interleaving Conversion
    def toBitInterleaving(self, laneLow, laneHigh):
        """Function to convert two 32-bit halves into two 32-bit interleaved words."""
        laneLow = int(laneLow)
        laneHigh = int(laneHigh)
        even = 0
        odd = 0
        for i in range(64):
            bit = 0
            if i < 32:
                bit = (laneLow >> i) & 1
            else:
                bit = (laneHigh >> (i - 32)) & 1
            if i % 2 == 0:
                even |= (bit << (i // 2))
            else:
                odd |= (bit << ((i-1) // 2))
        return even, odd
    
    def leak_toBitInterleaving(self, laneLow, laneHigh):
        """Function to convert two 32-bit halves into two 32-bit interleaved words with simulated leakage."""
        if not self.leak_bit_interleaving:
            return self.toBitInterleaving(laneLow, laneHigh)
        laneLow = int(laneLow)
        laneHigh = int(laneHigh)
        even = 0
        odd = 0
        for i in range(64):
            bit = 0
            if i < 32:
                bit = self.leak((laneLow >> i) & 1)
            else:
                bit = self.leak((laneHigh >> (i - 32)) & 1)
            if i % 2 == 0:
                even |= (self.leak(bit << (i // 2)))
            else:
                odd |= (self.leak(bit << ((i-1) // 2)))
        return even, odd
    
    def fromBitInterleaving(self, even_in, odd_in):
        """Function to convert two 32-bit interleaved words back into low/high 32-bit halves."""
        even_in = int(even_in)
        odd_in = int(odd_in)
        laneLow = 0
        laneHigh = 0
        for i in range(64):
            bit = 0
            if i % 2 == 0:
                bit = (even_in >> (i // 2)) & 1
            else:
                bit = (odd_in >> ((i-1) // 2)) & 1
            if i < 32:
                laneLow |= (bit << i)
            else:
                laneHigh |= (bit << (i - 32))
        return laneLow, laneHigh
    
    def leak_fromBitInterleaving(self, even_in, odd_in):
        """Function to convert two 32-bit interleaved words back into low/high 32-bit halves with simulated leakage."""
        if not self.leak_bit_interleaving:
            return self.fromBitInterleaving(even_in, odd_in)
        even_in = int(even_in)
        odd_in = int(odd_in)
        laneLow = 0
        laneHigh = 0
        for i in range(64):
            bit = 0
            if i % 2 == 0:
                bit = self.leak((even_in >> (i // 2)) & 1)
            else:
                bit = self.leak((odd_in >> ((i-1) // 2)) & 1)
            if i < 32:
                laneLow |= self.leak(bit << i)
            else:
                laneHigh |= self.leak(bit << (i - 32))
        return laneLow, laneHigh
    
    def index(self, x, y, z):
        """Function to compute the index in the State array for given coordinates (x, y, z)."""
        return ((((x)%5)+5*((y)%5))*2 + z)

    def _ensure_writable_buffer(self, buffer_obj, name):
        """Validate that buffer_obj supports in-place item assignment."""
        if not isinstance(buffer_obj, (np.ndarray, bytearray, list)):
            raise TypeError(f"{name} must be a writable buffer (numpy array, bytearray, or list)")

    # --- Keccak Permutation Steps (Theta, Rho, Pi, Chi, Iota) ---
    def theta(self, State):
        """Function to perform the Theta step of the Keccak permutation on the given State in-place."""
        C = np.zeros((5,2), dtype=np.uint32)
        D = np.zeros((5,2), dtype=np.uint32)
        for x in range(0, 5):
            for z in range(0, 2):
                for y in range(0, 5):
                    C[x][z] ^= State[self.index(x, y, z)]
        for x in range(0, 5):
            D[x][0], D[x][1] = self.ROL64(C[(x+1)%5][0], C[(x+1)%5][1], 1)
            for z in range(0, 2):
                D[x][z] ^= C[(x+4)%5][z]
        for x in range(0, 5):
            for y in range(0, 5):
                for z in range(0, 2):
                    State[self.index(x, y, z)] ^= D[x][z]

    def leak_theta(self, State):
        """Function to perform the Theta step of the Keccak permutation on the given State with simulated leakage in-place."""
        state_check = None
        if DEBUG:
            state_check = np.array(State, dtype=np.uint32, copy=True)
        C = np.zeros((5,2), dtype=np.uint32)
        D = np.zeros((5,2), dtype=np.uint32)
        for x in range(0, 5):
            for z in range(0, 2):
                for y in range(0, 5):
                    C[x][z] = self.leak_xor(C[x][z], State[self.index(x, y, z)])
        for x in range(0, 5):
            D[x][0], D[x][1] = self.leak_ROL64(C[(x+1)%5][0], C[(x+1)%5][1], 1)
            for z in range(0, 2):
                D[x][z] = self.leak_xor(D[x][z], C[(x+4)%5][z])
        for x in range(0, 5):
            for y in range(0, 5):
                for z in range(0, 2):
                    State[self.index(x, y, z)] = self.leak_xor(State[self.index(x, y, z)], D[x][z])
        if DEBUG:
            self.theta(state_check)
            if not np.array_equal(np.array(State, dtype=np.uint32), state_check):
                print("Error in leak_theta!")

    def rho(self, State):
        """Function to perform the Rho step of the Keccak permutation on the given State in-place."""
        for x in range(0, 5):
            for y in range(0, 5):
                State[self.index(x, y, 0)], State[self.index(x, y, 1)] = self.ROL64(State[self.index(x, y, 0)], State[self.index(x, y, 1)], self.RhoOffsets[x+5*y])

    def leak_rho(self, State):
        """Function to perform the Rho step of the Keccak permutation on the given State with simulated leakage in-place."""
        state_check = None
        if DEBUG:
            state_check = np.array(State, dtype=np.uint32, copy=True)
        for x in range(0, 5):
            for y in range(0, 5):
                State[self.index(x, y, 0)], State[self.index(x, y, 1)] = self.leak_ROL64(State[self.index(x, y, 0)], State[self.index(x, y, 1)], self.RhoOffsets[x+5*y])
        if DEBUG:
            self.rho(state_check)
            if not np.array_equal(np.array(State, dtype=np.uint32), state_check):
                print("Error in leak_rho!")
    
    def pi(self, State):
        """Function to perform the Pi step of the Keccak permutation on the given State in-place."""
        temp_State = np.zeros(50, dtype=np.uint32)
        for x in range(0, 5):
            for y in range(0, 5):
                for z in range(0, 2):
                    temp_State[self.index(x, y, z)] = State[self.index(x, y, z)]
        for x in range(0, 5):
            for y in range(0, 5):
                for z in range(0, 2):
                    State[self.index(0*x+1*y, 2*x+3*y, z)] = temp_State[self.index(x, y, z)]

    def leak_pi(self, State):
        """Function to perform the Pi step of the Keccak permutation on the given State with simulated leakage in-place."""
        if not self.leak_permutation_moves:
            self.pi(State)
            return
        state_check = None
        if DEBUG:
            state_check = np.array(State, dtype=np.uint32, copy=True)
        temp_State = np.zeros(50, dtype=np.uint32)
        for x in range(0, 5):
            for y in range(0, 5):
                for z in range(0, 2):
                    temp_State[self.index(x, y, z)] = self.leak(State[self.index(x, y, z)])
        for x in range(0, 5):
            for y in range(0, 5):
                for z in range(0, 2):
                    State[self.index(0*x+1*y, 2*x+3*y, z)] = self.leak(temp_State[self.index(x, y, z)])
        if DEBUG:
            self.pi(state_check)
            if not np.array_equal(np.array(State, dtype=np.uint32), state_check):
                print("Error in leak_pi!")
    
    def chi(self, State):
        """Function to perform the Chi step of the Keccak permutation on the given State in-place."""
        C = np.zeros((5,2), dtype=np.uint32)
        for y in range(0, 5):
            for x in range(0, 5):
                for z in range(0, 2):
                    C[x][z] = State[self.index(x, y, z)] ^ ((~State[self.index((x+1), y, z)]) & State[self.index((x+2), y, z)])
            for x in range(0, 5):
                for z in range(0, 2):
                    State[self.index(x, y, z)] = C[x][z]

    def leak_chi(self, State):
        """Function to perform the Chi step of the Keccak permutation on the given State with simulated leakage in-place."""
        state_check = None
        if DEBUG:
            state_check = np.array(State, dtype=np.uint32, copy=True)
        C = np.zeros((5,2), dtype=np.uint32)
        for y in range(0, 5):
            for x in range(0, 5):
                for z in range(0, 2):
                    C[x][z] = self.leak_xor(State[self.index(x, y, z)], self.leak_and(self.leak_not(State[self.index((x+1), y, z)]), State[self.index((x+2), y, z)]))
            for x in range(0, 5):
                for z in range(0, 2):
                    State[self.index(x, y, z)] = self.leak(C[x][z])
        if DEBUG:
            self.chi(state_check)
            if not np.array_equal(np.array(State, dtype=np.uint32), state_check):
                print("Error in leak_chi!")

    def iota(self, State, round_idx):
        """Function to perform the Iota step of the Keccak permutation on the given State in-place."""
        State[self.index(0, 0, 0)] ^= self.KeccakRoundConstants[round_idx][0]
        State[self.index(0, 0, 1)] ^= self.KeccakRoundConstants[round_idx][1]

    def leak_iota(self, State, round_idx):
        """Function to perform the Iota step of the Keccak permutation on the given State with simulated leakage in-place."""
        state_check = None
        if DEBUG:
            state_check = np.array(State, dtype=np.uint32, copy=True)
        State[self.index(0, 0, 0)] = self.leak_xor(State[self.index(0, 0, 0)], self.KeccakRoundConstants[round_idx][0])
        State[self.index(0, 0, 1)] = self.leak_xor(State[self.index(0, 0, 1)], self.KeccakRoundConstants[round_idx][1])
        if DEBUG:
            self.iota(state_check, round_idx)
            if not np.array_equal(np.array(State, dtype=np.uint32), state_check):
                print("Error in leak_iota!")

    # --- SPONGE CONSTRUCTION ---

    def KeccakP1600_AddBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        """Function to add bytes to a specific lane in the State."""
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            LOW, HIGH = 0, 0
            lane = np.zeros(2, dtype=np.uint32)
            for i in range(length):
                laneAsBytes[offset + i] = data[dataOffset + i]
            LOW = int(laneAsBytes[0]) | (int(laneAsBytes[1]) << 8) | (int(laneAsBytes[2]) << 16) | (int(laneAsBytes[3]) << 24)
            HIGH = int(laneAsBytes[4]) | (int(laneAsBytes[5]) << 8) | (int(laneAsBytes[6]) << 16) | (int(laneAsBytes[7]) << 24)
            lane[0], lane[1] = self.toBitInterleaving(LOW, HIGH)
            State[lanePosition*2] ^= lane[0]
            State[lanePosition*2 + 1] ^= lane[1]
        else:
            print("Error in KeccakP1600_AddBytesInLane: Invalid lanePosition, offset or length!")

    def leak_KeccakP1600_AddBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        """Function to add bytes to a specific lane in the State with simulated leakage."""
        if not self.leak_memory_moves:
            self.KeccakP1600_AddBytesInLane(State, lanePosition, data, dataOffset, offset, length)
            return
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            LOW, HIGH = 0, 0
            lane = np.zeros(2, dtype=np.uint32)
            for i in range(length):
                laneAsBytes[offset + i] = self.leak(data[dataOffset + i])
            LOW = self.leak(int(laneAsBytes[0]) | (int(laneAsBytes[1]) << 8) | (int(laneAsBytes[2]) << 16) | (int(laneAsBytes[3]) << 24))
            HIGH = self.leak(int(laneAsBytes[4]) | (int(laneAsBytes[5]) << 8) | (int(laneAsBytes[6]) << 16) | (int(laneAsBytes[7]) << 24))
            lane[0], lane[1] = self.leak_toBitInterleaving(LOW, HIGH)
            State[lanePosition*2] = self.leak_xor(State[lanePosition*2], lane[0])
            State[lanePosition*2 + 1] = self.leak_xor(State[lanePosition*2 + 1], lane[1])
        else:
            print("Error in leak_KeccakP1600_AddBytesInLane: Invalid lanePosition, offset or length!")

    def KeccakP1600_AddBytes(self, State, data, offset, length, dataOffset=0):
        """Function to add bytes to the State starting from a specific offset. It calculates the lane position and offset within the lane, and calls KeccakP1600_AddBytesInLane until all bytes are added."""
        lanePosition = offset//8
        offsetInLane = offset%8
        while (length > 0):
            bytesInLane = 8 - offsetInLane
            if (bytesInLane > length):
                bytesInLane = length
            self.KeccakP1600_AddBytesInLane(State, lanePosition, data, dataOffset, offsetInLane, bytesInLane)
            length -= bytesInLane
            lanePosition += 1
            offsetInLane = 0
            dataOffset += bytesInLane

    def leak_KeccakP1600_AddBytes(self, State, data, offset, length, dataOffset=0):
        """Function to add bytes to the State starting from a specific offset with simulated leakage. It calculates the lane position and offset within the lane, and calls leak_KeccakP1600_AddBytesInLane until all bytes are added."""
        lanePosition = offset//8
        offsetInLane = offset%8
        while (length > 0):
            bytesInLane = 8 - offsetInLane
            if (bytesInLane > length):
                bytesInLane = length
            self.leak_KeccakP1600_AddBytesInLane(State, lanePosition, data, dataOffset, offsetInLane, bytesInLane)
            length -= bytesInLane
            lanePosition += 1
            offsetInLane = 0
            dataOffset += bytesInLane
    
    def KeccakP1600_ExtractBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        """Function to extract bytes from a specific lane in the State."""
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            lane = np.zeros(2, dtype=np.uint32)
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            lane[0], lane[1] = self.fromBitInterleaving(State[lanePosition*2], State[lanePosition*2 + 1])
            laneAsBytes[0] = lane[0] & 0xFF
            laneAsBytes[1] = (lane[0] >> 8) & 0xFF
            laneAsBytes[2] = (lane[0] >> 16) & 0xFF
            laneAsBytes[3] = (lane[0] >> 24) & 0xFF
            laneAsBytes[4] = lane[1] & 0xFF
            laneAsBytes[5] = (lane[1] >> 8) & 0xFF
            laneAsBytes[6] = (lane[1] >> 16) & 0xFF
            laneAsBytes[7] = (lane[1] >> 24) & 0xFF
            for i in range(length):
                data[dataOffset + i] = laneAsBytes[offset + i]
        else:
            print("Error in KeccakP1600_ExtractBytesInLane: Invalid lanePosition, offset or length!")

    def leak_KeccakP1600_ExtractBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        """Function to extract bytes from a specific lane in the State with simulated leakage."""
        if not self.leak_memory_moves:
            self.KeccakP1600_ExtractBytesInLane(State, lanePosition, data, dataOffset, offset, length)
            return
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            lane = np.zeros(2, dtype=np.uint32)
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            lane[0], lane[1] = self.leak_fromBitInterleaving(State[lanePosition*2], State[lanePosition*2 + 1])
            laneAsBytes[0] = lane[0] & 0xFF
            laneAsBytes[1] = (lane[0] >> 8) & 0xFF
            laneAsBytes[2] = (lane[0] >> 16) & 0xFF
            laneAsBytes[3] = (lane[0] >> 24) & 0xFF
            laneAsBytes[4] = lane[1] & 0xFF
            laneAsBytes[5] = (lane[1] >> 8) & 0xFF
            laneAsBytes[6] = (lane[1] >> 16) & 0xFF
            laneAsBytes[7] = (lane[1] >> 24) & 0xFF
            for i in range(length):
                data[dataOffset + i] = self.leak(laneAsBytes[offset + i])
        else:
            print("Error in leak_KeccakP1600_ExtractBytesInLane: Invalid lanePosition, offset or length!")
        
    def KeccakP1600_ExtractBytes(self, State, data, offset, length, dataOffset=0):
        """Function to extract bytes from the State starting from a specific offset. It calculates the lane position and offset within the lane, and calls KeccakP1600_ExtractBytesInLane until all bytes are extracted."""
        self._ensure_writable_buffer(data, "data")
        lanePosition = offset//8
        offsetInLane = offset%8
        while (length > 0):
            bytesInLane = 8 - offsetInLane
            if (bytesInLane > length):
                bytesInLane = length
            self.KeccakP1600_ExtractBytesInLane(State, lanePosition, data, dataOffset, offsetInLane, bytesInLane)
            length -= bytesInLane
            lanePosition += 1
            offsetInLane = 0
            dataOffset += bytesInLane

    def leak_KeccakP1600_ExtractBytes(self, State, data, offset, length, dataOffset=0):
        """Function to extract bytes from the State starting from a specific offset with simulated leakage. It calculates the lane position and offset within the lane, and calls leak_KeccakP1600_ExtractBytesInLane until all bytes are extracted."""
        self._ensure_writable_buffer(data, "data")
        lanePosition = offset//8
        offsetInLane = offset%8
        while (length > 0):
            bytesInLane = 8 - offsetInLane
            if (bytesInLane > length):
                bytesInLane = length
            self.leak_KeccakP1600_ExtractBytesInLane(State, lanePosition, data, dataOffset, offsetInLane, bytesInLane)
            length -= bytesInLane
            lanePosition += 1
            offsetInLane = 0
            dataOffset += bytesInLane
    
    def KeccakP1600_ExtractAndAddBytesInLane(self, State, lanePosition, input, inputOffset, output, outputOffset, offset, length):
        """Function to extract bytes from a specific lane in the State and add them to the input data."""
        if ((lanePosition < 25) and (offset < 8) and (offset + length <= 8)):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            self.KeccakP1600_ExtractBytesInLane(State, lanePosition, laneAsBytes, 0, offset, length)
            for i in range(length):
                output[outputOffset + i] = input[inputOffset + i] ^ laneAsBytes[i]
        else:
            print("Error in KeccakP1600_ExtractAndAddBytesInLane: Invalid lanePosition, offset or length!")

    def leak_KeccakP1600_ExtractAndAddBytesInLane(self, State, lanePosition, input, inputOffset, output, outputOffset, offset, length):
        """Function to extract bytes from a specific lane in the State and add them to the input data with simulated leakage."""
        if not self.leak_memory_moves:
            self.KeccakP1600_ExtractAndAddBytesInLane(State, lanePosition, input, inputOffset, output, outputOffset, offset, length)
            return
        if ((lanePosition < 25) and (offset < 8) and (offset + length <= 8)):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            self.leak_KeccakP1600_ExtractBytesInLane(State, lanePosition, laneAsBytes, 0, offset, length)
            for i in range(length):
                output[outputOffset + i] = self.leak(input[inputOffset + i] ^ laneAsBytes[i])
        else:
            print("Error in leak_KeccakP1600_ExtractAndAddBytesInLane: Invalid lanePosition, offset or length!")

    def KeccakP1600_ExtractAndAddBytes(self, State, input, output, offset, length, inputOffset=0, outputOffset=0):
        """Function to extract bytes from the State starting from a specific offset and add them to the input data."""
        self._ensure_writable_buffer(output, "output")
        lanePosition = offset//8
        offsetInLane = offset%8

        while (length > 0):
            bytesInLane = 8 - offsetInLane
            if (bytesInLane > length):
                bytesInLane = length
            self.KeccakP1600_ExtractAndAddBytesInLane(State, lanePosition, input, inputOffset, output, outputOffset, offsetInLane, bytesInLane)
            length -= bytesInLane
            lanePosition += 1
            offsetInLane = 0
            inputOffset += bytesInLane
            outputOffset += bytesInLane

    def leak_KeccakP1600_ExtractAndAddBytes(self, State, input, output, offset, length, inputOffset=0, outputOffset=0):
        """Function to extract bytes from the State starting from a specific offset and add them to the input data with simulated leakage."""
        self._ensure_writable_buffer(output, "output")
        lanePosition = offset//8
        offsetInLane = offset%8

        while (length > 0):
            bytesInLane = 8 - offsetInLane
            if (bytesInLane > length):
                bytesInLane = length
            self.leak_KeccakP1600_ExtractAndAddBytesInLane(State, lanePosition, input, inputOffset, output, outputOffset, offsetInLane, bytesInLane)
            length -= bytesInLane
            lanePosition += 1
            offsetInLane = 0
            inputOffset += bytesInLane
            outputOffset += bytesInLane

    def KeccakP1600_OverwriteBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        """Function to overwrite bytes in a specific lane in the State."""
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            LOW, HIGH = 0, 0
            lane = np.zeros(2, dtype=np.uint32)
            
            self.KeccakP1600_ExtractBytesInLane(State, lanePosition, laneAsBytes, 0, 0, 8)
            for i in range(length):
                laneAsBytes[offset + i] = data[dataOffset + i]
            LOW = int(laneAsBytes[0]) | (int(laneAsBytes[1]) << 8) | (int(laneAsBytes[2]) << 16) | (int(laneAsBytes[3]) << 24)
            HIGH = int(laneAsBytes[4]) | (int(laneAsBytes[5]) << 8) | (int(laneAsBytes[6]) << 16) | (int(laneAsBytes[7]) << 24)
            lane[0], lane[1] = self.toBitInterleaving(LOW, HIGH)
            State[lanePosition*2] = lane[0]
            State[lanePosition*2 + 1] = lane[1]
        else:
            print("Error in KeccakP1600_OverwriteBytesInLane: Invalid lanePosition, offset or length!")

    def leak_KeccakP1600_OverwriteBytesInLane(self, State, lanePosition, data, dataOffset, offset, length):
        """Function to overwrite bytes in a specific lane in the State with simulated leakage."""
        if not self.leak_memory_moves:
            self.KeccakP1600_OverwriteBytesInLane(State, lanePosition, data, dataOffset, offset, length)
            return
        if (lanePosition < 25) and (offset < 8) and (offset + length <= 8):
            laneAsBytes = np.zeros(8, dtype=np.uint8)
            LOW, HIGH = 0, 0
            lane = np.zeros(2, dtype=np.uint32)
            
            self.leak_KeccakP1600_ExtractBytesInLane(State, lanePosition, laneAsBytes, 0, 0, 8)
            for i in range(length):
                laneAsBytes[offset + i] = self.leak(data[dataOffset + i])
            LOW = self.leak(int(laneAsBytes[0]) | (int(laneAsBytes[1]) << 8) | (int(laneAsBytes[2]) << 16) | (int(laneAsBytes[3]) << 24))
            HIGH = self.leak(int(laneAsBytes[4]) | (int(laneAsBytes[5]) << 8) | (int(laneAsBytes[6]) << 16) | (int(laneAsBytes[7]) << 24))
            lane[0], lane[1] = self.leak_toBitInterleaving(LOW, HIGH)
            State[lanePosition*2] = self.leak(lane[0])
            State[lanePosition*2 + 1] = self.leak(lane[1])
        else:
            print("Error in leak_KeccakP1600_OverwriteBytesInLane: Invalid lanePosition, offset or length!")
        
    def KeccakP1600_OverwriteBytes(self, State, data, offset, length, dataOffset=0):
        """Function to overwrite bytes in the State starting from a specific offset. It calculates the lane position and offset within the lane, and calls KeccakP1600_OverwriteBytesInLane until all bytes are overwritten."""
        lanePosition = offset//8
        offsetInLane = offset%8
        while (length > 0):
            bytesInLane = 8 - offsetInLane
            if (bytesInLane > length):
                bytesInLane = length
            self.KeccakP1600_OverwriteBytesInLane(State, lanePosition, data, dataOffset, offsetInLane, bytesInLane)
            length -= bytesInLane
            lanePosition += 1
            offsetInLane = 0
            dataOffset += bytesInLane
    
    def leak_KeccakP1600_OverwriteBytes(self, State, data, offset, length, dataOffset=0):
        """Function to overwrite bytes in the State starting from a specific offset with simulated leakage. It calculates the lane position and offset within the lane, and calls leak_KeccakP1600_OverwriteBytesInLane until all bytes are overwritten."""
        lanePosition = offset//8
        offsetInLane = offset%8
        while (length > 0):
            bytesInLane = 8 - offsetInLane
            if (bytesInLane > length):
                bytesInLane = length
            self.leak_KeccakP1600_OverwriteBytesInLane(State, lanePosition, data, dataOffset, offsetInLane, bytesInLane)
            length -= bytesInLane
            lanePosition += 1
            offsetInLane = 0
            dataOffset += bytesInLane
    
    def KeccakP1600_OverwriteWithZeroes(self, State, byteCount):
        """Function to overwrite bytes in the State with zeroes."""
        laneAsBytes = np.zeros(8, dtype=np.uint8)
        lanePosition = 0

        while (byteCount > 0):
            if (byteCount < 8):
                self.KeccakP1600_OverwriteBytesInLane(State, lanePosition, laneAsBytes, 0, 0, byteCount)
                byteCount = 0
            else:
                State[lanePosition*2] = 0
                State[lanePosition*2 + 1] = 0
                byteCount -= 8
                lanePosition += 1

    def leak_KeccakP1600_OverwriteWithZeroes(self, State, byteCount):
        """Function to overwrite bytes in the State with zeroes with simulated leakage."""
        if not self.leak_memory_moves:
            self.KeccakP1600_OverwriteWithZeroes(State, byteCount)
            return
        laneAsBytes = np.zeros(8, dtype=np.uint8)
        lanePosition = 0

        while (byteCount > 0):
            if (byteCount < 8):
                self.leak_KeccakP1600_OverwriteBytesInLane(State, lanePosition, laneAsBytes, 0, 0, byteCount)
                byteCount = 0
            else:
                State[lanePosition*2] = self.leak(0)
                State[lanePosition*2 + 1] = self.leak(0)
                byteCount -= 8
                lanePosition += 1
    
    def KeccakP1600_Permute_24rounds(self, State):
        """Function to perform the Keccak permutation with 24 rounds on the given State. It calls Keccak_PermutationOnWords with 24 rounds to compute the new State after the permutation."""
        self.KeccakP1600_PermutationOnWords(State, 24)
    
    def KeccakP1600_Permute_Nrounds(self, State, rounds):
        """Function to perform the Keccak permutation with a specified number of rounds on the given State. It calls Keccak_PermutationOnWords with the specified number of rounds to compute the new State after the permutation."""
        self.KeccakP1600_PermutationOnWords(State, rounds)
    
    def KeccakP1600_PermutationOnWords(self, State, rounds):
        """Function to perform the Keccak permutation on the given State with a specified number of rounds. It iteratively applies the Theta, Rho, Pi, Chi, and Iota transformations for the specified number of rounds to compute the new State after the permutation."""
        for i in range(24-rounds, 24):
            self.theta(State)
            self.rho(State)
            self.pi(State)
            self.chi(State)
            self.iota(State, i)

    def KeccakP1600_leak_PermutationOnWords(self, State, rounds):
        """Function to perform the Keccak permutation on the given State with simulated leakage for a specified number of rounds. It iteratively applies the Theta, Rho, Pi, Chi, and Iota transformations with simulated leakage for the specified number of rounds to compute the new State after the permutation."""
        self.invocation_sample_index = 0
        invocation_start = len(self.trace)
        for i in range(24-rounds, 24):
            self.leak_theta(State)
            self.leak_rho(State)
            self.leak_pi(State)
            self.leak_chi(State)
            self.leak_iota(State, i)
        self.invocation_trace_ranges.append((invocation_start, len(self.trace)))

    def KeccakP1600_Initialize(self, State):
        """Function to initialize the State in-place by setting all lanes to zero."""
        for i in range(50):
            State[i] = 0

    def leak_KeccakP1600_Initialize(self, State):
        """Function to initialize the State in-place with simulated leakage by setting all lanes to zero."""
        if not self.leak_init:
            self.KeccakP1600_Initialize(State)
            return
        for i in range(50):
            State[i] = self.leak(0)
    
    def SpongeInitialize(self, rate, capacity):
        """Function to initialize the State for the sponge construction. It calls KeccakP1600_Initialize to set the State to a static value."""
        if (rate + capacity != 1600):
            print("Error in SpongeInitialize: Invalid rate and capacity combination!")
            return 1
        if ((rate <= 0) or (rate >= 1600) or ((rate % 8) != 0)):
            print("Error in SpongeInitialize: Invalid rate value!")
            return 1
        self.State = np.zeros(50, dtype=np.uint32)
        self.KeccakP1600_Initialize(self.State)
        self.rate = rate
        self.byteIOIndex = 0
        self.squeezing = False
        return 0
    
    def leak_SpongeInitialize(self, rate, capacity):
        """Function to initialize the State for the sponge construction with simulated leakage. It calls leak_KeccakP1600_Initialize to set the State to a static value with simulated leakage."""
        if (rate + capacity != 1600):
            print("Error in leak_SpongeInitialize: Invalid rate and capacity combination!")
            return 1
        if ((rate <= 0) or (rate >= 1600) or ((rate % 8) != 0)):
            print("Error in leak_SpongeInitialize: Invalid rate value!")
            return 1
        self.State = np.zeros(50, dtype=np.uint32)
        self.leak_KeccakP1600_Initialize(self.State)
        self.rate = rate
        self.byteIOIndex = 0
        self.squeezing = False
        return 0
    
    def SpongeAbsorb(self, data, dataByteLen):
        """Function to absorb data into the State for the sponge construction. It calls KeccakP1600_AddBytes to add the data to the State and KeccakP1600_Permute_24rounds to permute the State after absorbing each block of data."""
        if (self.squeezing):
            print("Error in SpongeAbsorb: Cannot absorb data after squeezing has started!")
            return 1
        partialBlock = 0
        curDataOffset = 0
        rateInBytes = self.rate // 8

        i = 0
        while (i < dataByteLen):
            if ((self.byteIOIndex == 0) and (dataByteLen - i >= rateInBytes)):
                while (dataByteLen - i >= rateInBytes):
                    self.KeccakP1600_AddBytes(self.State, data, 0, rateInBytes, curDataOffset)
                    self.KeccakP1600_PermutationOnWords(self.State, 24)
                    curDataOffset += rateInBytes
                    i += rateInBytes
            else:
                if (dataByteLen-i > rateInBytes-self.byteIOIndex):
                    partialBlock = rateInBytes - self.byteIOIndex
                else:
                    partialBlock = dataByteLen - i
                i += partialBlock
                self.KeccakP1600_AddBytes(self.State, data, self.byteIOIndex, partialBlock, curDataOffset)
                self.byteIOIndex += partialBlock
                curDataOffset += partialBlock
                if (self.byteIOIndex == rateInBytes):
                    self.KeccakP1600_PermutationOnWords(self.State, 24)
                    self.byteIOIndex = 0
        return 0
    
    def leak_SpongeAbsorb(self, data, dataByteLen):
        """Function to absorb data into the State for the sponge construction with simulated leakage. It calls leak_KeccakP1600_AddBytes to add the data to the State with simulated leakage and KeccakP1600_Permute_24rounds to permute the State after absorbing each block of data."""
        if (self.squeezing):
            print("Error in leak_SpongeAbsorb: Cannot absorb data after squeezing has started!")
            return 1
        partialBlock = 0
        curDataOffset = 0
        rateInBytes = self.rate // 8

        i = 0
        while (i < dataByteLen):
            if ((self.byteIOIndex == 0) and (dataByteLen - i >= rateInBytes)):
                while (dataByteLen - i >= rateInBytes):
                    self.leak_KeccakP1600_AddBytes(self.State, data, 0, rateInBytes, curDataOffset)
                    self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
                    curDataOffset += rateInBytes
                    i += rateInBytes
            else:
                if (dataByteLen-i > rateInBytes-self.byteIOIndex):
                    partialBlock = rateInBytes - self.byteIOIndex
                else:
                    partialBlock = dataByteLen - i
                i += partialBlock
                self.leak_KeccakP1600_AddBytes(self.State, data, self.byteIOIndex, partialBlock, curDataOffset)
                self.byteIOIndex += partialBlock
                curDataOffset += partialBlock
                if (self.byteIOIndex == rateInBytes):
                    self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
                    self.byteIOIndex = 0
        return 0
    
    def SpongeAbsorbLastFewBits(self, delimitedData):
        """Function to absorb the last few bits of data into the State for the sponge construction. It calls KeccakP1600_AddBytes to add the delimited data to the State and KeccakP1600_Permute_24rounds to permute the State after absorbing the last few bits of data."""
        rateInBytes = self.rate // 8
        if (delimitedData == 0):
            print("Error in SpongeAbsorbLastFewBits: delimitedData cannot be zero!")
            return 1
        if (self.squeezing):
            print("Error in SpongeAbsorbLastFewBits: Cannot absorb data after squeezing has started!")
            return 1
        self.KeccakP1600_AddBytes(self.State, [delimitedData], self.byteIOIndex, 1)
        if ((delimitedData >= 0x80) and (self.byteIOIndex == (rateInBytes - 1))):
            self.KeccakP1600_PermutationOnWords(self.State, 24)
        self.KeccakP1600_AddBytes(self.State, [0x80], (rateInBytes - 1), 1)
        self.KeccakP1600_PermutationOnWords(self.State, 24)
        self.byteIOIndex = 0
        self.squeezing = True
        return 0
    
    def leak_SpongeAbsorbLastFewBits(self, delimitedData):
        """Function to absorb the last few bits of data into the State for the sponge construction with simulated leakage. It calls leak_KeccakP1600_AddBytes to add the delimited data to the State with simulated leakage and KeccakP1600_Permute_24rounds to permute the State after absorbing the last few bits of data."""
        rateInBytes = self.rate // 8
        if (delimitedData == 0):
            print("Error in leak_SpongeAbsorbLastFewBits: delimitedData cannot be zero!")
            return 1
        if (self.squeezing):
            print("Error in leak_SpongeAbsorbLastFewBits: Cannot absorb data after squeezing has started!")
            return 1
        self.leak_KeccakP1600_AddBytes(self.State, [delimitedData], self.byteIOIndex, 1)
        if ((delimitedData >= 0x80) and (self.byteIOIndex == (rateInBytes - 1))):
            self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
        self.leak_KeccakP1600_AddBytes(self.State, [0x80], (rateInBytes - 1), 1)
        self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
        self.byteIOIndex = 0
        self.squeezing = True
        return 0
    
    def SpongeSqueeze(self, data, dataByteLen):
        """Function to squeeze data out of the State for the sponge construction. It calls KeccakP1600_ExtractBytes to extract data from the State and KeccakP1600_Permute_24rounds to permute the State after squeezing each block of data."""
        i = 0
        partialBlock = 0
        rateInBytes = self.rate // 8
        curDataOffset = 0

        if (not self.squeezing):
            if self.SpongeAbsorbLastFewBits(0x01) != 0:
                print("Error in SpongeSqueeze: Failed to switch to squeezing phase!")
                return 1
    
        while (i < dataByteLen):
            if ((self.byteIOIndex == rateInBytes) and (dataByteLen - i >= rateInBytes)):
                for j in range(dataByteLen-i, rateInBytes, -rateInBytes):
                    self.KeccakP1600_PermutationOnWords(self.State, 24)
                    self.KeccakP1600_ExtractBytes(self.State, data, 0, rateInBytes, curDataOffset)
                    curDataOffset += rateInBytes
                i = dataByteLen - j
            else:
                if (self.byteIOIndex == rateInBytes):
                    self.KeccakP1600_PermutationOnWords(self.State, 24)
                    self.byteIOIndex = 0
                if (dataByteLen - i > rateInBytes-self.byteIOIndex):
                    partialBlock = rateInBytes - self.byteIOIndex
                else:
                    partialBlock = dataByteLen - i
                i += partialBlock
                self.KeccakP1600_ExtractBytes(self.State, data, self.byteIOIndex, partialBlock, curDataOffset)
                curDataOffset += partialBlock
                self.byteIOIndex += partialBlock
        return 0
    
    def leak_SpongeSqueeze(self, data, dataByteLen):
        """Function to squeeze data out of the State for the sponge construction with simulated leakage. It calls leak_KeccakP1600_ExtractBytes to extract data from the State with simulated leakage and KeccakP1600_Permute_24rounds to permute the State after squeezing each block of data."""
        i = 0
        partialBlock = 0
        rateInBytes = self.rate // 8
        curDataOffset = 0

        if (not self.squeezing):
            if self.leak_SpongeAbsorbLastFewBits(0x01) != 0:
                print("Error in leak_SpongeSqueeze: Failed to switch to squeezing phase!")
                return 1
    
        while (i < dataByteLen):
            if ((self.byteIOIndex == rateInBytes) and (dataByteLen - i >= rateInBytes)):
                for j in range(dataByteLen-i, rateInBytes, -rateInBytes):
                    self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
                    self.leak_KeccakP1600_ExtractBytes(self.State, data, 0, rateInBytes, curDataOffset)
                    curDataOffset += rateInBytes
                i = dataByteLen - j
            else:
                if (self.byteIOIndex == rateInBytes):
                    self.KeccakP1600_leak_PermutationOnWords(self.State, 24)
                    self.byteIOIndex = 0
                if (dataByteLen - i > rateInBytes-self.byteIOIndex):
                    partialBlock = rateInBytes - self.byteIOIndex
                else:
                    partialBlock = dataByteLen - i
                i += partialBlock
                self.leak_KeccakP1600_ExtractBytes(self.State, data, self.byteIOIndex, partialBlock, curDataOffset)
                curDataOffset += partialBlock
                self.byteIOIndex += partialBlock
        return 0

    def SHA3(self, d, M):
        """Compute SHA3-d where M is a hex string."""
        if d not in (224, 256, 384, 512):
            print(f"Undefined size of SHA3: {d}")
            return "XX"
        capacity = 2 * d
        rate = 1600 - capacity
        if self.SpongeInitialize(rate, capacity) != 0:
            return "XX"
        msg_bytes = bytes.fromhex(M)
        msg_buf = np.frombuffer(msg_bytes, dtype=np.uint8)
        if self.SpongeAbsorb(msg_buf, len(msg_bytes)) != 0:
            return "XX"
        if self.SpongeAbsorbLastFewBits(0x06) != 0:
            return "XX"
        out = np.zeros(d // 8, dtype=np.uint8)
        if self.SpongeSqueeze(out, d // 8) != 0:
            return "XX"
        return bytes(out).hex()
    
    def leak_SHA3(self, d, M):
        """Compute SHA3-d with simulated leakage where M is a hex string."""
        if d not in (224, 256, 384, 512):
            print(f"Undefined size of SHA3: {d}")
            return "XX"
        capacity = 2 * d
        rate = 1600 - capacity
        if self.leak_SpongeInitialize(rate, capacity) != 0:
            return "XX"
        msg_bytes = bytes.fromhex(M)
        msg_buf = np.frombuffer(msg_bytes, dtype=np.uint8)
        if self.leak_SpongeAbsorb(msg_buf, len(msg_bytes)) != 0:
            return "XX"
        if self.leak_SpongeAbsorbLastFewBits(0x06) != 0:
            return "XX"
        out = np.zeros(d // 8, dtype=np.uint8)
        if self.leak_SpongeSqueeze(out, d // 8) != 0:
            return "XX"
        return bytes(out).hex()

    def SHAKE(self, s, M, d):
        """Compute SHAKE-s with output length d bits where M is a hex string."""
        if s not in (128, 256):
            print(f"Undefined size of SHAKE: {s}")
            return "XX"
        if (d % 8) != 0:
            print("Error in SHAKE: output size must be byte-aligned")
            return "XX"
        capacity = 2 * s
        rate = 1600 - capacity
        if self.SpongeInitialize(rate, capacity) != 0:
            return "XX"
        msg_bytes = bytes.fromhex(M)
        msg_buf = np.frombuffer(msg_bytes, dtype=np.uint8)
        if self.SpongeAbsorb(msg_buf, len(msg_bytes)) != 0:
            return "XX"
        if self.SpongeAbsorbLastFewBits(0x1F) != 0:
            return "XX"
        out = np.zeros(d // 8, dtype=np.uint8)
        if self.SpongeSqueeze(out, d // 8) != 0:
            return "XX"
        return bytes(out).hex()
    
    def leak_SHAKE(self, s, M, d):
        """Compute SHAKE-s with simulated leakage and output length d bits where M is a hex string."""
        if s not in (128, 256):
            print(f"Undefined size of SHAKE: {s}")
            return "XX"
        if (d % 8) != 0:
            print("Error in leak_SHAKE: output size must be byte-aligned")
            return "XX"
        capacity = 2 * s
        rate = 1600 - capacity
        if self.leak_SpongeInitialize(rate, capacity) != 0:
            return "XX"
        msg_bytes = bytes.fromhex(M)
        msg_buf = np.frombuffer(msg_bytes, dtype=np.uint8)
        if self.leak_SpongeAbsorb(msg_buf, len(msg_bytes)) != 0:
            return "XX"
        if self.leak_SpongeAbsorbLastFewBits(0x1F) != 0:
            return "XX"
        out = np.zeros(d // 8, dtype=np.uint8)
        if self.leak_SpongeSqueeze(out, d // 8) != 0:
            return "XX"
        return bytes(out).hex()

    def SHA3_224(self, M):
        return self.SHA3(224, M)

    def generate_trace_SHA3_224(self, M, output_file=None, separator="\n", append=False, trace_format="text", trace_dtype="int16"):
        self.reset()
        self.leak_SHA3(224, M)
        self._finalize_trace()
        if output_file is not None:
            self.write_trace_to_file(
                output_file,
                separator=separator,
                append=append,
                trace_format=trace_format,
                trace_dtype=trace_dtype,
            )
        return self.trace

    def SHA3_256(self, M):
        return self.SHA3(256, M)

    def generate_trace_SHA3_256(self, M, output_file=None, separator="\n", append=False, trace_format="text", trace_dtype="int16"):
        self.reset()
        self.leak_SHA3(256, M)
        self._finalize_trace()
        if output_file is not None:
            self.write_trace_to_file(
                output_file,
                separator=separator,
                append=append,
                trace_format=trace_format,
                trace_dtype=trace_dtype,
            )
        return self.trace

    def SHA3_384(self, M):
        return self.SHA3(384, M)

    def generate_trace_SHA3_384(self, M, output_file=None, separator="\n", append=False, trace_format="text", trace_dtype="int16"):
        self.reset()
        self.leak_SHA3(384, M)
        self._finalize_trace()
        if output_file is not None:
            self.write_trace_to_file(
                output_file,
                separator=separator,
                append=append,
                trace_format=trace_format,
                trace_dtype=trace_dtype,
            )
        return self.trace

    def SHA3_512(self, M):
        return self.SHA3(512, M)

    def generate_trace_SHA3_512(self, M, output_file=None, separator="\n", append=False, trace_format="text", trace_dtype="int16"):
        self.reset()
        self.leak_SHA3(512, M)
        self._finalize_trace()
        if output_file is not None:
            self.write_trace_to_file(
                output_file,
                separator=separator,
                append=append,
                trace_format=trace_format,
                trace_dtype=trace_dtype,
            )
        return self.trace

    def SHAKE128(self, M, B):
        # B: output size in bytes.
        return self.SHAKE(128, M, B * 8)

    def SHAKE256(self, M, B):
        # B: output size in bytes.
        return self.SHAKE(256, M, B * 8)

def _build_cli_parser():
    parser = argparse.ArgumentParser(
        description="Keccak trace simulator CLI (BI variant)",
    )
    parser.add_argument(
        "--algorithm",
        choices=["sha3-224", "sha3-256", "sha3-384", "sha3-512", "shake128", "shake256"],
        help="Algorithm to run",
    )
    parser.add_argument(
        "--input-hex",
        help="Input message as a hex string (without 0x prefix)",
    )
    parser.add_argument(
        "--input-text",
        help="Input message as UTF-8 text",
    )
    parser.add_argument(
        "--bytes",
        type=int,
        default=32,
        help="Output bytes for SHAKE algorithms (default: 32)",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Generate leakage trace in addition to digest",
    )
    parser.add_argument(
        "--trace-file",
        help="Optional path to write trace values",
    )
    parser.add_argument(
        "--trace-format",
        choices=["text", "bin"],
        default="text",
        help="Trace file format (default: text)",
    )
    parser.add_argument(
        "--trace-dtype",
        default="int16",
        help="Numpy dtype for binary trace writing (default: int16)",
    )
    parser.add_argument(
        "--trace-separator",
        default="\n",
        help="Separator used when writing trace to file (default: newline)",
    )
    parser.add_argument(
        "--append-trace",
        action="store_true",
        help="Append trace to existing trace file",
    )
    parser.add_argument(
        "--noise",
        type=float,
        default=0,
        help="Constant noise added to each leakage sample",
    )
    parser.add_argument(
        "--noise-sigma",
        type=float,
        default=0.0,
        help="Std-dev of per-sample Gaussian noise added to leakage samples",
    )
    parser.add_argument(
        "--gain-jitter-sigma",
        type=float,
        default=0.0,
        help="Std-dev of per-trace multiplicative gain jitter",
    )
    parser.add_argument(
        "--offset-jitter-sigma",
        type=float,
        default=0.0,
        help="Std-dev of per-trace additive offset jitter",
    )
    parser.add_argument(
        "--smooth-window",
        type=int,
        default=1,
        help="Moving-average window length applied to each generated trace (default: 1 = disabled)",
    )
    parser.add_argument(
        "--hw-scale",
        type=float,
        default=1.0,
        help="Scale for data-dependent HW term (default: 1.0)",
    )
    parser.add_argument(
        "--common-wave-scale",
        type=float,
        default=0.0,
        help="Scale for deterministic common-mode waveform added to each sample (default: 0.0)",
    )
    parser.add_argument(
        "--common-wave-period",
        type=int,
        default=256,
        help="Period (in samples) of common-mode waveform (default: 256)",
    )
    parser.add_argument(
        "--common-wave-scope",
        choices=["trace", "invocation"],
        default="trace",
        help="Common-wave phase scope: trace (global) or invocation (reset each permutation invocation)",
    )
    parser.add_argument(
        "--hw-ratio",
        type=float,
        default=None,
        help="Optional single-knob mix: HW contribution ratio in [0,1]; common-wave ratio is (1-ratio)",
    )
    parser.add_argument(
        "--leakage-profile",
        choices=["full", "focused", "logic-only"],
        default="full",
        help="Leakage source profile: full or focused/logic-only (default: full)",
    )
    parser.add_argument(
        "--leakage-granularity",
        choices=["word", "byte", "byte-bitweighted", "word-bitweighted"],
        default="word",
        help="Per-leak() sample shape. 'word'/'byte' emit Hamming-weight only "
             "(SR ceiling ~1/70 for byte classification). The '-bitweighted' "
             "variants emit Σ wᵢ·bitᵢ with seeded weights wᵢ ∈ U(0,1), "
             "matching the Schindler/Lemke/Paar stochastic model and lifting "
             "the SR ceiling proportional to SNR. (default: word).",
    )
    parser.add_argument(
        "--seed-pbw",
        type=int,
        default=None,
        help="RNG seed for per-bit weights used by the '-bitweighted' "
             "granularities. Same seed → same weights → templates trained "
             "against one seed match data from the same seed. (default: 0xB17)",
    )
    parser.add_argument(
        "--pbw-shared",
        action="store_true",
        help="Legacy: use a single shared 8-vec (byte) / 32-vec (word) of "
             "per-bit weights for all leakage points (collapsed F_9). "
             "Default off ⇒ per-leakage-point weights drawn lazily from "
             "the seeded RNG. Use this only to reproduce pre-Apr-29 "
             "archived runs (smoke widerpbw, paperscale_*, etc.).",
    )
    parser.add_argument(
        "--pbw-c8-range",
        type=float,
        default=0.5,
        help="Half-width of U(-r, +r) for the per-leakage-point intercept "
             "c_8(t) in F_9. Set to 0 for weights-only per-position pbw "
             "(no independent baseline variation). Ignored when "
             "--pbw-shared is set. (default: 0.5)",
    )
    parser.add_argument(
        "--corr-probe-traces",
        type=int,
        default=0,
        help="Generate N traces and report corr statistics against the first trace (debug/tuning mode)",
    )
    parser.add_argument(
        "--bulk-count",
        type=int,
        default=0,
        help="Deprecated legacy option (do not use)",
    )
    parser.add_argument(
        "--bulk-total-traces",
        type=int,
        default=None,
        help="Deprecated legacy option (do not use)",
    )
    parser.add_argument(
        "--bulk-invocations",
        type=int,
        default=None,
        help="Target number of Keccak permutation invocations per trace (SHA3 only)",
    )
    parser.add_argument(
        "--bulk-folders",
        type=int,
        default=None,
        help="Number of output folders to generate",
    )
    parser.add_argument(
        "--bulk-traces-per-folder",
        type=int,
        default=None,
        help="Number of traces to generate in each output folder",
    )
    parser.add_argument(
        "--random-input-bytes",
        type=int,
        default=32,
        help="Random input length in bytes for bulk mode (default: 32)",
    )
    parser.add_argument(
        "--bulk-output-dir",
        default="bulk_traces",
        help="Directory where bulk trace files are written",
    )
    parser.add_argument(
        "--bulk-index-file",
        default=None,
        help="Optional CSV path for bulk metadata index (default: <bulk-output-dir>/.index.csv)",
    )
    parser.add_argument(
        "--bulk-index-dir",
        default=None,
        help="Optional directory for bulk metadata index files (writes index_XXXX.csv per folder)",
    )
    parser.add_argument(
        "--bulk-seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible random inputs",
    )
    parser.add_argument(
        "--bulk-data-format",
        choices=["uint8", "hex"],
        default="hex",
        help="Format for data_in.npy and data_out.npy in bulk mode (default: uint8)",
    )
    return parser


def _parse_message_hex(args, parser):
    if args.input_hex is not None and args.input_text is not None:
        parser.error("Use only one of --input-hex or --input-text")

    if args.input_text is not None:
        return args.input_text.encode("utf-8").hex()

    if args.input_hex is not None:
        try:
            bytes.fromhex(args.input_hex)
        except ValueError as exc:
            parser.error(f"Invalid hex input: {exc}")
        return args.input_hex

    parser.error("One of --input-hex or --input-text is required")


def _run_single(simulator, algo, message_hex, args, trace_output_file=None):
    trace = None

    if algo == "sha3-224":
        if args.trace:
            trace = simulator.generate_trace_SHA3_224(
                message_hex,
                output_file=trace_output_file,
                separator=args.trace_separator,
                append=args.append_trace,
                trace_format=args.trace_format,
                trace_dtype=args.trace_dtype,
            )
            digest = simulator.SHA3_224(message_hex)
        else:
            digest = simulator.SHA3_224(message_hex)
    elif algo == "sha3-256":
        if args.trace:
            trace = simulator.generate_trace_SHA3_256(
                message_hex,
                output_file=trace_output_file,
                separator=args.trace_separator,
                append=args.append_trace,
                trace_format=args.trace_format,
                trace_dtype=args.trace_dtype,
            )
            digest = simulator.SHA3_256(message_hex)
        else:
            digest = simulator.SHA3_256(message_hex)
    elif algo == "sha3-384":
        if args.trace:
            trace = simulator.generate_trace_SHA3_384(
                message_hex,
                output_file=trace_output_file,
                separator=args.trace_separator,
                append=args.append_trace,
                trace_format=args.trace_format,
                trace_dtype=args.trace_dtype,
            )
            digest = simulator.SHA3_384(message_hex)
        else:
            digest = simulator.SHA3_384(message_hex)
    elif algo == "sha3-512":
        if args.trace:
            trace = simulator.generate_trace_SHA3_512(
                message_hex,
                output_file=trace_output_file,
                separator=args.trace_separator,
                append=args.append_trace,
                trace_format=args.trace_format,
                trace_dtype=args.trace_dtype,
            )
            digest = simulator.SHA3_512(message_hex)
        else:
            digest = simulator.SHA3_512(message_hex)
    elif algo == "shake128":
        digest = simulator.SHAKE128(message_hex, args.bytes)
    elif algo == "shake256":
        digest = simulator.SHAKE256(message_hex, args.bytes)
    else:
        raise ValueError(f"Unsupported algorithm: {algo}")

    return digest, trace


def _rate_in_bytes_for_sha3_algorithm(algo):
    if algo == "sha3-224":
        return (1600 - 2 * 224) // 8
    if algo == "sha3-256":
        return (1600 - 2 * 256) // 8
    if algo == "sha3-384":
        return (1600 - 2 * 384) // 8
    if algo == "sha3-512":
        return (1600 - 2 * 512) // 8
    raise ValueError(f"Unsupported SHA3 algorithm for rate computation: {algo}")


def _derive_random_input_bytes_for_invocations(algo, invocations):
    if invocations <= 0:
        raise ValueError("bulk invocations must be > 0")
    rate_in_bytes = _rate_in_bytes_for_sha3_algorithm(algo)
    # For SHA3 with fixed-size output, invocation_count = floor(message_len / rate) + 1.
    if invocations == 1:
        return 1
    return (invocations - 1) * rate_in_bytes


def _run_corr_probe(simulator, algo, args, parser):
    if args.corr_probe_traces <= 1:
        parser.error("--corr-probe-traces must be > 1")
    if not args.trace:
        parser.error("--corr-probe-traces requires --trace")
    if algo in ("shake128", "shake256"):
        parser.error("--corr-probe-traces is currently implemented only for SHA3 algorithms")

    probe_input_bytes = args.random_input_bytes
    if args.bulk_invocations is not None:
        try:
            probe_input_bytes = _derive_random_input_bytes_for_invocations(algo, args.bulk_invocations)
        except ValueError as exc:
            parser.error(str(exc))

    rng = np.random.default_rng(args.bulk_seed)
    ref_trace = None
    corrs = []
    for _ in range(args.corr_probe_traces):
        msg_bytes = rng.integers(0, 256, size=probe_input_bytes, dtype=np.uint8).tobytes()
        message_hex = msg_bytes.hex()
        _, trace = _run_single(simulator, algo, message_hex, args, trace_output_file=None)
        arr = np.asarray(trace, dtype=np.float64)
        if ref_trace is None:
            ref_trace = arr
            continue
        if len(arr) != len(ref_trace):
            parser.error("Correlation probe got inconsistent trace lengths")
        corrs.append(float(np.corrcoef(arr, ref_trace)[0][1]))

    corr_array = np.asarray(corrs, dtype=np.float64)
    print("corr_probe_trace_len={}".format(len(ref_trace)))
    print("corr_probe_count={}".format(len(corr_array)))
    print("corr_probe_mean={:.6f}".format(float(np.mean(corr_array))))
    print("corr_probe_std={:.6f}".format(float(np.std(corr_array))))
    print("corr_probe_min={:.6f}".format(float(np.min(corr_array))))
    print("corr_probe_p05={:.6f}".format(float(np.percentile(corr_array, 5.0))))
    print("corr_probe_median={:.6f}".format(float(np.median(corr_array))))
    print("corr_probe_p95={:.6f}".format(float(np.percentile(corr_array, 95.0))))
    print("corr_probe_max={:.6f}".format(float(np.max(corr_array))))


def main():
    parser = _build_cli_parser()
    args = parser.parse_args()

    simulator = KeccakTraceSimulator(
        noise_level=args.noise,
        noise_sigma=args.noise_sigma,
        gain_jitter_sigma=args.gain_jitter_sigma,
        offset_jitter_sigma=args.offset_jitter_sigma,
        smooth_window=args.smooth_window,
        hw_scale=args.hw_scale,
        common_wave_scale=args.common_wave_scale,
        common_wave_period=args.common_wave_period,
        common_wave_scope=args.common_wave_scope,
        hw_ratio=args.hw_ratio,
        leakage_profile=args.leakage_profile,
        leakage_granularity=args.leakage_granularity,
        rng_seed=args.bulk_seed,
        seed_pbw=args.seed_pbw,
        pbw_shared=args.pbw_shared,
        pbw_c8_range=args.pbw_c8_range,
    )

    if args.algorithm is None:
        parser.error("--algorithm is required")

    algo = args.algorithm

    if args.trace and algo in ("shake128", "shake256"):
        parser.error("Trace generation is currently implemented only for SHA3 algorithms")

    if args.trace and args.trace_format == "bin":
        try:
            np.dtype(args.trace_dtype)
        except TypeError as exc:
            parser.error(f"Invalid --trace-dtype: {exc}")

    if args.smooth_window <= 0:
        parser.error("--smooth-window must be >= 1")

    if args.common_wave_period <= 0:
        parser.error("--common-wave-period must be >= 1")

    if args.hw_ratio is not None and (args.hw_ratio < 0.0 or args.hw_ratio > 1.0):
        parser.error("--hw-ratio must be within [0,1]")

    if args.corr_probe_traces < 0:
        parser.error("--corr-probe-traces must be >= 0")

    if args.bulk_count < 0:
        parser.error("--bulk-count must be >= 0")

    if args.bulk_total_traces is not None and args.bulk_total_traces < 0:
        parser.error("--bulk-total-traces must be >= 0")

    if args.bulk_folders is not None and args.bulk_folders <= 0:
        parser.error("--bulk-folders must be > 0")

    if args.bulk_traces_per_folder is not None and args.bulk_traces_per_folder <= 0:
        parser.error("--bulk-traces-per-folder must be > 0")

    if args.bulk_invocations is not None and args.bulk_invocations <= 0:
        parser.error("--bulk-invocations must be > 0")

    if args.random_input_bytes <= 0:
        parser.error("--random-input-bytes must be > 0")

    if args.bytes <= 0 and algo in ("shake128", "shake256"):
        parser.error("--bytes must be > 0 for SHAKE")

    bulk_mode_requested = (
        args.bulk_folders is not None
        or args.bulk_traces_per_folder is not None
        or args.bulk_total_traces is not None
        or args.bulk_count > 0
    )

    if args.corr_probe_traces > 0:
        _run_corr_probe(simulator, algo, args, parser)
        return 0

    if bulk_mode_requested:
        if not args.trace:
            parser.error("Bulk mode is for trace generation; use --trace")
        if algo in ("shake128", "shake256"):
            parser.error("Bulk trace generation is currently implemented only for SHA3 algorithms")
        if args.input_hex is not None or args.input_text is not None:
            parser.error("Do not provide --input-hex/--input-text in bulk mode")
        if args.trace_file is not None:
            parser.error("Use --bulk-output-dir in bulk mode instead of --trace-file")

        if args.bulk_total_traces is not None or args.bulk_count > 0:
            parser.error("--bulk-total-traces and --bulk-count are deprecated; use --bulk-folders with --bulk-traces-per-folder")

        if args.bulk_folders is None or args.bulk_traces_per_folder is None:
            parser.error("Bulk mode requires both --bulk-folders and --bulk-traces-per-folder")

        effective_bulk_folders = args.bulk_folders
        traces_per_folder = args.bulk_traces_per_folder
        bulk_total_traces = effective_bulk_folders * traces_per_folder

        if args.bulk_index_file is not None and args.bulk_index_dir is not None:
            parser.error("Use only one of --bulk-index-file or --bulk-index-dir")
        if args.bulk_index_file is not None and effective_bulk_folders > 1:
            parser.error("--bulk-index-file can be used only when exactly one output folder is generated")

        bulk_random_input_bytes = args.random_input_bytes
        if args.bulk_invocations is not None:
            try:
                bulk_random_input_bytes = _derive_random_input_bytes_for_invocations(algo, args.bulk_invocations)
            except ValueError as exc:
                parser.error(str(exc))

        rng = np.random.default_rng(args.bulk_seed)
        base_output_dir = Path(args.bulk_output_dir)
        index_dir = None
        if args.bulk_index_dir is not None:
            index_dir = Path(args.bulk_index_dir)
            index_dir.mkdir(parents=True, exist_ok=True)

        folder_summaries = []
        global_sample = 0
        for folder_idx in range(effective_bulk_folders):
            traces_in_folder = traces_per_folder
            folder_path = Path(f"{args.bulk_output_dir}{folder_idx:04d}")
            folder_path.mkdir(parents=True, exist_ok=True)

            if args.bulk_index_file is not None and effective_bulk_folders == 1:
                index_path = Path(args.bulk_index_file)
            elif index_dir is not None:
                index_path = index_dir / f"index_{folder_idx:04d}.csv"
            else:
                index_path = folder_path / ".index.csv"
            data_in_path = folder_path / "data_in.npy"
            data_out_path = folder_path / "data_out.npy"

            data_in_rows = []
            data_out_rows = []
            with index_path.open("w", newline="", encoding="utf-8") as index_file:
                writer = csv.writer(index_file)
                writer.writerow(["sample", "global_sample", "input_hex", "digest", "trace_files", "invocation_trace_lens", "trace_len_total", "invocation_count"])

                for folder_sample in range(traces_in_folder):
                    msg_bytes = rng.integers(0, 256, size=bulk_random_input_bytes, dtype=np.uint8).tobytes()
                    message_hex = msg_bytes.hex()
                    digest, trace = _run_single(simulator, algo, message_hex, args, trace_output_file=None)

                    invocation_traces = simulator.get_invocation_traces()
                    invocation_trace_files = []
                    invocation_trace_lens = []
                    trace_suffix = "bin" if args.trace_format == "bin" else "txt"
                    for invocation, invocation_trace in enumerate(invocation_traces):
                        trace_path = folder_path / f"trace_{folder_sample:04d}_{invocation}_ch0.{trace_suffix}"
                        simulator.write_trace_values_to_file(
                            invocation_trace,
                            trace_path,
                            separator=args.trace_separator,
                            trace_format=args.trace_format,
                            trace_dtype=args.trace_dtype,
                        )
                        invocation_trace_files.append(str(trace_path))
                        invocation_trace_lens.append(len(invocation_trace))

                    if args.bulk_invocations is not None and len(invocation_traces) != args.bulk_invocations:
                        parser.error(
                            f"Unable to satisfy --bulk-invocations={args.bulk_invocations} for {algo}; "
                            f"observed {len(invocation_traces)} invocations"
                        )

                    if args.bulk_data_format == "hex":
                        data_in_rows.append(message_hex)
                        data_out_rows.append(digest)
                    else:
                        data_in_rows.append(np.frombuffer(msg_bytes, dtype=np.uint8).copy())
                        data_out_rows.append(np.frombuffer(bytes.fromhex(digest), dtype=np.uint8).copy())
                    writer.writerow([
                        folder_sample,
                        global_sample,
                        message_hex,
                        digest,
                        ";".join(invocation_trace_files),
                        ";".join(str(v) for v in invocation_trace_lens),
                        len(trace),
                        len(invocation_traces),
                    ])
                    global_sample += 1

            if args.bulk_data_format == "hex":
                data_in = np.asarray(data_in_rows, dtype=str)
                data_out = np.asarray(data_out_rows, dtype=str)
            else:
                if data_in_rows:
                    data_in = np.asarray(data_in_rows, dtype=np.uint8)
                else:
                    data_in = np.zeros((0, bulk_random_input_bytes), dtype=np.uint8)

                if data_out_rows:
                    data_out = np.asarray(data_out_rows, dtype=np.uint8)
                else:
                    data_out_digest_bytes = {
                        "sha3-224": 28,
                        "sha3-256": 32,
                        "sha3-384": 48,
                        "sha3-512": 64,
                    }[algo]
                    data_out = np.zeros((0, data_out_digest_bytes), dtype=np.uint8)

            np.save(data_in_path, data_in)
            np.save(data_out_path, data_out)

            folder_summaries.append((folder_path, index_path, data_in_path, data_out_path, traces_in_folder))

        print(f"bulk_samples={bulk_total_traces}")
        print(f"total_traces_generated={bulk_total_traces}")
        print(f"bulk_output_base={base_output_dir}")
        print(f"bulk_folders={effective_bulk_folders}")
        print(f"bulk_traces_per_folder={traces_per_folder}")
        print(f"bulk_random_input_bytes={bulk_random_input_bytes}")
        print(f"bulk_data_format={args.bulk_data_format}")
        for folder_path, index_path, data_in_path, data_out_path, traces_in_folder in folder_summaries:
            print(f"folder={folder_path}")
            print(f"folder_samples={traces_in_folder}")
            print(f"bulk_index_file={index_path}")
            print(f"bulk_data_in_file={data_in_path}")
            print(f"bulk_data_out_file={data_out_path}")
        return 0

    message_hex = _parse_message_hex(args, parser)
    digest, trace = _run_single(simulator, algo, message_hex, args, trace_output_file=args.trace_file)

    print(digest)
    if args.trace:
        print(f"trace_len={len(trace)}")
        if args.trace_file is not None:
            print(f"trace_file={args.trace_file}")

    return 0


if __name__=='__main__':
    raise SystemExit(main())
