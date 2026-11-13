# EoT Model Comparison

## Pareto Frontier

![Pareto frontier](pareto_frontier.png)

## Best Cutoff Rate at Latency Budget

![Best cutoff rate at latency budgets](cutoff_rate_at_latency_budget_300_600ms.png)

| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **3.5%** | **1.2%** |
| ultraVAD | 12.0% | 3.5% |
| LiveKit Turn Detector v1.1-mini | 19.3% | 3.6% |
| OpenAI GPT Realtime 2 | - | - |
| Soniox | - | 6.6% |
| VAP (silent agent) | 48.8% | 10.2% |
| SmartTurn v3.2 | 34.9% | 11.2% |
| Gradium | 48.8% | 13.5% |
| Deepgram Flux | 20.6% | 12.7% |
| VAD baseline | 48.8% | 17.6% |

## Best Latency at Cutoff Budget

![Best latency at cutoff budgets](latency_at_cutoff_budget_5_10pct.png)

| Model | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **276 ms** | **220 ms** |
| ultraVAD | 462 ms | 347 ms |
| LiveKit Turn Detector v1.1-mini | 543 ms | 393 ms |
| OpenAI GPT Realtime 2 | 736 ms | 672 ms |
| Soniox | 792 ms | 583 ms |
| VAP (silent agent) | 796 ms | 619 ms |
| SmartTurn v3.2 | 837 ms | 622 ms |
| Gradium | 903 ms | 671 ms |
| Deepgram Flux | 1003 ms | 701 ms |
| VAD baseline | 1200 ms | 900 ms |

## Operating Points

| Type | Budget | Model | Mean Latency | Cutoff | Detect | Threshold | Action Delay | Timeout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1 | 0.276 | 4.9% | 95.8% | 0.320 | 0.200 | 2.000 |
| Cutoff | 5.0% | ultraVAD | 0.462 | 4.8% | 90.4% | 0.260 | 0.300 | 2.000 |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1-mini | 0.543 | 4.8% | 73.6% | 0.450 | 0.200 | 1.500 |
| Cutoff | 5.0% | OpenAI GPT Realtime 2 | 0.736 | 4.0% | 94.7% | 0.990 | 0.200 | 2.000 |
| Cutoff | 5.0% | Soniox | 0.792 | 2.4% | 58.1% | 0.990 | 0.200 | 1.500 |
| Cutoff | 5.0% | VAP (silent agent) | 0.796 | 4.8% | 90.2% | 0.070 | 0.500 | 1.500 |
| Cutoff | 5.0% | SmartTurn v3.2 | 0.837 | 4.9% | 82.9% | 0.040 | 0.700 | 1.500 |
| Cutoff | 5.0% | Gradium | 0.903 | 4.9% | 91.9% | 0.330 | 0.700 | 2.000 |
| Cutoff | 5.0% | Deepgram Flux | 1.003 | 4.9% | 99.7% | 0.670 | 1.000 | 2.000 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1 | 0.220 | 9.1% | 98.9% | 0.130 | 0.200 | 2.000 |
| Cutoff | 10.0% | ultraVAD | 0.347 | 9.5% | 91.9% | 0.230 | 0.200 | 2.000 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1-mini | 0.393 | 9.4% | 75.8% | 0.440 | 0.200 | 1.000 |
| Cutoff | 10.0% | OpenAI GPT Realtime 2 | 0.672 | 8.5% | 90.2% | 0.990 | 0.200 | 1.000 |
| Cutoff | 10.0% | Soniox | 0.583 | 6.6% | 58.1% | 0.990 | 0.200 | 1.000 |
| Cutoff | 10.0% | VAP (silent agent) | 0.619 | 9.8% | 97.8% | 0.050 | 0.300 | 2.000 |
| Cutoff | 10.0% | SmartTurn v3.2 | 0.622 | 9.9% | 62.9% | 0.680 | 0.400 | 1.000 |
| Cutoff | 10.0% | Gradium | 0.671 | 9.9% | 98.3% | 0.180 | 0.600 | 1.500 |
| Cutoff | 10.0% | Deepgram Flux | 0.701 | 9.8% | 100.0% | 0.570 | 0.700 | 1.500 |
| Latency | 300ms | LiveKit Turn Detector v1.1 | 0.291 | 3.5% | 94.9% | 0.460 | 0.200 | 2.000 |
| Latency | 300ms | ultraVAD | 0.291 | 12.0% | 93.0% | 0.220 | 0.200 | 1.500 |
| Latency | 300ms | LiveKit Turn Detector v1.1-mini | 0.295 | 19.3% | 92.7% | 0.210 | 0.200 | 1.500 |
| Latency | 300ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 300ms | Soniox | - | - | - | - | - | - |
| Latency | 300ms | VAP (silent agent) | 0.300 | 48.8% | 100.0% | 0.000 | 0.300 | 1.000 |
| Latency | 300ms | SmartTurn v3.2 | 0.294 | 34.9% | 88.2% | 0.020 | 0.200 | 1.000 |
| Latency | 300ms | Gradium | 0.300 | 48.8% | 100.0% | 0.000 | 0.300 | 1.000 |
| Latency | 300ms | Deepgram Flux | 0.299 | 20.6% | 99.7% | 0.620 | 0.200 | 1.500 |
| Latency | 600ms | LiveKit Turn Detector v1.1 | 0.579 | 1.2% | 78.9% | 0.870 | 0.200 | 2.000 |
| Latency | 600ms | ultraVAD | 0.577 | 3.5% | 83.7% | 0.320 | 0.300 | 2.000 |
| Latency | 600ms | LiveKit Turn Detector v1.1-mini | 0.590 | 3.6% | 75.8% | 0.440 | 0.300 | 1.500 |
| Latency | 600ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 600ms | Soniox | 0.583 | 6.6% | 58.1% | 0.990 | 0.200 | 1.000 |
| Latency | 600ms | VAP (silent agent) | 0.585 | 10.2% | 98.3% | 0.040 | 0.400 | 2.000 |
| Latency | 600ms | SmartTurn v3.2 | 0.595 | 11.2% | 57.9% | 0.840 | 0.300 | 1.000 |
| Latency | 600ms | Gradium | 0.593 | 13.5% | 99.4% | 0.140 | 0.500 | 2.000 |
| Latency | 600ms | Deepgram Flux | 0.591 | 12.7% | 92.1% | 0.710 | 0.500 | 1.500 |
