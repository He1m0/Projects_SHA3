# GEMINI.md

## Project Overview
This project focuses on **Side-Channel Analysis (SCA)**, specifically **Template Attacks**, against implementations of the **SHA-3 (Keccak)** hash function family. It encompasses research and experiments on two different architectures:
- **32-bit (STM32F303RCT7/ARM Cortex-M4):** A mature implementation on a ChipWhisperer-Lite board.
- **8-bit (Atmel XMEGA 256 A3U):** An implementation designed for efficiency on 8-bit microcontrollers.

The repository includes a sophisticated Keccak trace simulator (`KeccakSim_BI_TA.py`) that models bit-interleaving and Hamming weight/distance leakage, which is crucial for simulating realistic power-consumption traces on 32-bit hardware.

## Architecture & Pipeline
The project is structured into numbered phases, typically executed via `script_all.sh` in each subdirectory.

### High-Level Flow
1. **0001 Reference:** Generates `ref_trace.npy` and performs correlation filtering to define "good" traces.
2. **0002 Detection:** Uses **Multiple Linear Regression ($R^2$)** to identify **Points of Interest (PoI)** or **Interesting Clock Cycles (ICS)**.
3. **0003 Training:** Build **LDA Templates**. Reassembles traces by concatenating samples from the ICS identified in phase 0002.
4. **0004 Validation:** Evaluates template quality using **First-Order Success Rate (SR)** and **Guessing Entropy (GE)**.
5. **0005 SASCA:** Performs **Soft Analytical Side-Channel Analysis** using **Loopy Belief Propagation** on factor graphs to recover state bits.
6. **0006-0011 Attacks:** Application of the verified templates and factor graphs to specific SHA-3 and SHAKE variants.

### Key Technical Concepts
- **8-bit Fragmentation:** To make the attack on a 32-bit word tractable, the pipeline attacks each word as **4 byte fragments x 256 classes** rather than $2^{32}$ classes.
- **Intermediate Value Families:**
    - **Family C/D:** Linear parity vectors inside the $\theta$ step. Low information yield but clean structure.
    - **Family A:** Full state after $\theta + \rho + \pi$ (just before $\chi$). High SR due to leakage spreading after permutation.
    - **Family B:** Round output (after $\chi$). **Most valuable** because $\chi$ is the non-linear step in Keccak.
- **Bit-Interleaving:** The 32-bit ARM implementation uses an interleaved representation of the 64-bit Keccak lanes, which is modeled in the simulator.

## Research Findings (Simulator vs. Real Silicon)
- **The Information Gap:** Real silicon achieves ~35% A-family Success Rate, while the simulator caps at ~10% with LDA-256 byte templates.
- **Leakage Models:**
    - **Hamming Weight (HW):** Baseline model.
    - **Hamming Distance (HD):** Transition-based leakage. 
        - **Substitution-based HD:** (Old) Replaces HW with HD. Degrades performance.
        - **Additive HD:** (New) $L = HW(value) + \alpha \cdot HW(value \oplus prev\_value)$. Controlled by `SIM_HD_ADD_SCALE`.
    - **Multi-cycle Leakage:** Models pipeline leakage by repeating emissions across cycles. Controlled by `SIM_LEAK_REPEAT`.
    - **Bit-Weighted (Stochastic Model):** Per-bit weights ($U(0,1)$) in the simulator significantly improve SASCA outcomes compared to pure HW.
- **ICS Strictness:** `ICS_LEVEL=40` (threshold 0.04 $R^2$) is identified as a "sweet spot" for balancing runtime and signal capture, especially for deep rounds (Round 4) where signal is diffuse.
- **Bottlenecks:** Research indicates the bottleneck for simulator fidelity is **Information per Sample** (e.g., bit-pair interactions, microarchitectural fingerprints) rather than sample count or template configuration.

## Dependencies
- **Python 3:** `numpy`, `h5py`, `matplotlib`, `scikit-learn`.
- **Shell:** Bash for pipeline orchestration.
- **Storage:** Large datasets are managed in `Processed_HDF5/` and `Raw/` (git-ignored). A Linux server with at least 2 TB storage is recommended for full experiments.

## Building and Running
### Configuration
Centralized in `project_SHA3-32bit/global_config.py`. Use `.env` files (see `pipeline_runner/envs/`) for profiles.
```bash
# Example: Use a specific smoke test profile
cp project_SHA3-32bit/pipeline_runner/envs/.env_smoke project_SHA3-32bit/.env
```

### Execution
Use the `pipeline_runner` for automated end-to-end runs:
```bash
cd project_SHA3-32bit/pipeline_runner
./run_full_pipeline.sh --env-file ./envs/.env_smoke_per_leakpoint
```

### Calibration
The **Fast Calibration Matrix (M0-M3)** (see `CALIBRATION_MATRIX_FAST.md`) is used to isolate bottlenecks across ICS strictness, correlation gates, and simulator knobs.

## Development Conventions
- **Trace Consistency:** All phases validate traces against `ref_trace.npy` from Phase 0001.
- **Automation First:** Use `script_all.sh` and `clean.sh` in subdirectories for manual phase execution.
- **Data Integrity:** Intermediate results are typically stored in HDF5 or archived ZIPs (e.g., `Bit_Tables.zip`, `templateLDA_O010.zip`).
