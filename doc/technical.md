# Technical Details

[← Back to README](../README.md) | [Algorithms](algorithms.md)

This document covers the parallelization strategy and performance tooling used by the simulator.

## Parallel Simulation

Monte Carlo simulations are "embarrassingly parallel" — each trial is completely independent. The simulator distributes iteration batches across multiple CPU cores using Python's `multiprocessing`, achieving near-linear speedup.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Main Process                                │
│                                                                     │
│  total_iterations = 10,000    workers = 4                           │
│  batch_size = total_iterations / workers = 2,500                    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Split into batches                        │    │
│  └────┬──────────┬──────────────┬──────────────┬───────────────┘    │
│       │          │              │              │                     │
│       ▼          ▼              ▼              ▼                     │
│  ┌────────┐ ┌────────┐    ┌────────┐    ┌────────┐                 │
│  │Worker 1│ │Worker 2│    │Worker 3│    │Worker 4│                 │
│  │2,500   │ │2,500   │    │2,500   │    │2,500   │                 │
│  │trials  │ │trials  │    │trials  │    │trials  │                 │
│  │        │ │        │    │        │    │        │                 │
│  │Own RNG │ │Own RNG │    │Own RNG │    │Own RNG │                 │
│  └────┬───┘ └────┬───┘    └────┬───┘    └────┬───┘                 │
│       │          │              │              │                     │
│       ▼          ▼              ▼              ▼                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                     Merge results                           │    │
│  │  • Sum playoff counts across workers                        │    │
│  │  • Sum seeding matrices                                     │    │
│  │  • Combine scenario counters                                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  Impact games analysis also runs in parallel (one team per worker)  │
└─────────────────────────────────────────────────────────────────────┘
```

### How It Works

1. The total iteration count is split into equal batches (one per worker process)
2. Each worker process runs its batch independently with its own random number generator
3. When all workers finish, their results (playoff counts, seeding matrices, scenario counters) are merged by summing
4. Impact games analysis also runs in parallel (one team per worker)

### Configuration

The **Workers** slider in the UI controls how many CPU cores to use. It defaults to the machine's total core count and is capped at that value. Setting it to 1 disables parallelism entirely (useful for debugging).

### Performance

On a 4-core machine with 10,000 iterations:

| Workers | Time | Speedup |
|:---:|:---:|:---:|
| 1 | ~8.4s | 1.0x |
| 2 | ~5.0s | 1.7x |
| 4 | ~4.0s | 2.1x |

Sub-linear scaling is expected due to process startup overhead and result merging. The speedup improves with higher iteration counts where per-trial work dominates the fixed overhead.

### Platform Notes

| Platform | Process Creation | Notes |
|---|---|---|
| Linux | `fork` | Fast, copy-on-write memory sharing |
| Windows | `spawn` | Slightly slower startup (re-imports modules) |

Both produce identical simulation results.

---

## Solver Performance Export

The "Export Performance Data" button in the Clinching Scenarios section writes solver timing benchmarks to [`solver-performance.md`](solver-performance.md). This file is designed to be committed to the repository for cross-platform comparison.

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Clinching Solver Run                            │
│                                                                     │
│  Records per run:                                                   │
│  • Timing (ms/eval)                                                 │
│  • Method (enumeration / sampling)                                  │
│  • Worker count                                                     │
│  • CPU model (detected at runtime)                                  │
│                                                                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     SQLite Database                                  │
│                                                                     │
│  Rolling window: last 50 measurements per platform                  │
│                                                                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │  "Export Performance Data" clicked
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Export Logic                                       │
│                                                                     │
│  1. Group by (CPU Model, CPU Cores, Method)                         │
│  2. Compute median for each group                                   │
│  3. Compute "Factor" column (relative to overall median)            │
│  4. Preserve entries from other platforms already in the file        │
│  5. Write merged results to doc/solver-performance.md               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### How It Works

- Each clinching solver run stores its timing (ms/eval, method, worker count) in the local SQLite database (rolling window of 50 measurements)
- Clicking "Export Performance Data" computes the median for each unique (CPU Model, CPU Cores, Method) combination and writes one row per combination
- The file preserves entries from other platforms — check out on a different machine, run the solver, click Export, and both sets of results appear side-by-side
- The "Factor" column compares hardware groups: factor > 1.0 means faster than median, < 1.0 means slower
- "CPU Cores" reflects the number of workers used (set via the Workers slider in Simulation parameters), not necessarily the total hardware cores

### Output Format

The exported file ([`solver-performance.md`](solver-performance.md)) contains a markdown table:

| CPU Model | CPU Cores | Relevant Games | Wall Clock (s) | Method | Total Evals | Factor |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| Apple M3 Max | 14 | 9 | 5.00 | enumeration | 19683 | 0.6 |
| 12th Gen Intel(R) Core(TM) i5-1245U | 12 | 9 | 19.68 | enumeration | 19683 | 1.4 |

### Contributing Benchmarks

1. Run the clinching scenarios solver on your machine (at least a few times for stable medians)
2. Click "Export Performance Data"
3. Commit the updated `doc/solver-performance.md`
4. Your hardware's results will appear alongside others for comparison
