# EoT Model Comparison

## Pareto Frontier

![Pareto frontier](pareto_frontier.png)

## Best Cutoff Rate at Latency Budget

![Best cutoff rate at latency budgets](cutoff_rate_at_latency_budget_300_600ms.png)

| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **14.0%** | **5.2%** |
| LiveKit Turn Detector v1.1-mini | 20.4% | 9.4% |
| Soniox | - | 9.1% |
| SmartTurn v3.2 | 43.3% | 17.9% |
| ultraVAD | 44.9% | 18.5% |
| OpenAI GPT Realtime 2 | - | - |
| VAP (silent agent) | 50.4% | 20.4% |
| Gradium | 48.8% | 16.3% |
| VAD baseline | 55.6% | 21.8% |

## Best Latency at Cutoff Budget

![Best latency at cutoff budgets](latency_at_cutoff_budget_5_10pct.png)

| Model | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **601 ms** | **398 ms** |
| LiveKit Turn Detector v1.1-mini | 838 ms | 538 ms |
| Soniox | 913 ms | 584 ms |
| SmartTurn v3.2 | 1013 ms | 779 ms |
| ultraVAD | 1075 ms | 798 ms |
| OpenAI GPT Realtime 2 | 1094 ms | 877 ms |
| VAP (silent agent) | 1120 ms | 819 ms |
| Gradium | 1137 ms | 768 ms |
| VAD baseline | 1200 ms | 900 ms |

## Operating Points

| Type | Budget | Model | Mean Latency | Cutoff | Detect | Threshold | Action Delay | Timeout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1 | 0.601 | 5.0% | 77.8% | 0.810 | 0.200 | 2.000 |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1-mini | 0.838 | 5.0% | 77.5% | 0.610 | 0.500 | 2.000 |
| Cutoff | 5.0% | Soniox | 0.913 | 4.1% | 78.0% | 0.990 | 0.600 | 2.000 |
| Cutoff | 5.0% | SmartTurn v3.2 | 1.013 | 4.7% | 89.8% | 0.340 | 0.900 | 2.000 |
| Cutoff | 5.0% | ultraVAD | 1.075 | 5.0% | 85.0% | 0.120 | 1.000 | 1.500 |
| Cutoff | 5.0% | OpenAI GPT Realtime 2 | 1.094 | 5.0% | 90.8% | 0.990 | 1.000 | 2.000 |
| Cutoff | 5.0% | VAP (silent agent) | 1.120 | 4.7% | 80.5% | 0.090 | 1.000 | 1.500 |
| Cutoff | 5.0% | Gradium | 1.137 | 5.0% | 75.2% | 0.420 | 1.000 | 1.500 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1 | 0.398 | 9.9% | 84.8% | 0.700 | 0.200 | 1.500 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1-mini | 0.538 | 9.9% | 57.8% | 0.730 | 0.200 | 1.000 |
| Cutoff | 10.0% | Soniox | 0.584 | 9.1% | 77.8% | 0.990 | 0.200 | 1.500 |
| Cutoff | 10.0% | SmartTurn v3.2 | 0.779 | 9.9% | 73.5% | 0.910 | 0.700 | 1.000 |
| Cutoff | 10.0% | ultraVAD | 0.798 | 9.9% | 67.2% | 0.210 | 0.700 | 1.000 |
| Cutoff | 10.0% | OpenAI GPT Realtime 2 | 0.877 | 9.9% | 90.8% | 0.990 | 0.800 | 1.500 |
| Cutoff | 10.0% | VAP (silent agent) | 0.819 | 9.9% | 71.2% | 0.090 | 0.700 | 1.000 |
| Cutoff | 10.0% | Gradium | 0.768 | 9.9% | 86.8% | 0.310 | 0.500 | 1.500 |
| Latency | 300ms | LiveKit Turn Detector v1.1 | 0.286 | 14.0% | 95.2% | 0.290 | 0.200 | 2.000 |
| Latency | 300ms | LiveKit Turn Detector v1.1-mini | 0.294 | 20.4% | 88.2% | 0.430 | 0.200 | 1.000 |
| Latency | 300ms | Soniox | - | - | - | - | - | - |
| Latency | 300ms | SmartTurn v3.2 | 0.296 | 43.3% | 88.0% | 0.460 | 0.200 | 1.000 |
| Latency | 300ms | ultraVAD | 0.296 | 44.9% | 88.0% | 0.080 | 0.200 | 1.000 |
| Latency | 300ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 300ms | VAP (silent agent) | 0.293 | 50.4% | 99.5% | 0.020 | 0.200 | 1.500 |
| Latency | 300ms | Gradium | 0.293 | 48.8% | 99.5% | 0.020 | 0.200 | 1.500 |
| Latency | 600ms | LiveKit Turn Detector v1.1 | 0.578 | 5.2% | 79.0% | 0.800 | 0.200 | 2.000 |
| Latency | 600ms | LiveKit Turn Detector v1.1-mini | 0.596 | 9.4% | 50.5% | 0.760 | 0.200 | 1.000 |
| Latency | 600ms | Soniox | 0.584 | 9.1% | 77.8% | 0.990 | 0.200 | 1.500 |
| Latency | 600ms | SmartTurn v3.2 | 0.596 | 17.9% | 80.8% | 0.790 | 0.500 | 1.000 |
| Latency | 600ms | ultraVAD | 0.597 | 18.5% | 67.2% | 0.210 | 0.400 | 1.000 |
| Latency | 600ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 600ms | VAP (silent agent) | 0.589 | 20.4% | 91.8% | 0.040 | 0.500 | 1.000 |
| Latency | 600ms | Gradium | 0.595 | 16.3% | 93.8% | 0.170 | 0.500 | 1.000 |
