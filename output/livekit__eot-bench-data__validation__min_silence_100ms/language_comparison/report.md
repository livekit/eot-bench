# EoT Language Comparison

## Best cutoff rate @ 0.3s latency

![Best cutoff rate @ 0.3s latency heatmap](heatmap_best_cutoff_rate_at_0_3s_latency.png)

| Language | LiveKit Turn Detector v1 | LiveKit Turn Detector v1-mini | Deepgram Flux | ultraVAD | SmartTurn v3.2 | AssemblyAI | Soniox | OpenAI GPT Realtime 2 | Cartesia Ink 2 | Gradium | VAD baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ar | 16.2% | 24.4% | - | 45.5% | 39.2% | - | - | - | - | 54.8% | 54.8% |
| de | 11.8% | 24.8% | 14.6% | 35.5% | 35.5% | 44.2% | - | - | - | 53.6% | 53.6% |
| en | 9.9% | 27.8% | 12.9% | 27.7% | 35.2% | 49.4% | - | - | - | 55.6% | 55.6% |
| es | 15.5% | 26.0% | 16.4% | 41.6% | 38.7% | 52.5% | - | - | - | 58.9% | 58.9% |
| fr | 12.7% | 22.4% | 13.1% | 34.4% | 38.9% | 41.8% | - | - | - | 56.6% | 56.6% |
| hi | 10.5% | 27.4% | 19.2% | 39.1% | 42.6% | - | - | - | - | 49.5% | 49.5% |
| id | 22.3% | 43.5% | - | 45.0% | 46.2% | - | - | - | - | 59.5% | 59.5% |
| it | 16.9% | 33.7% | 27.3% | 40.4% | 44.1% | - | - | - | - | 55.0% | 55.0% |
| ja | 5.6% | 23.5% | 20.6% | 12.0% | 34.9% | - | - | - | - | 48.8% | 48.8% |
| ko | 5.5% | 12.3% | - | 33.8% | 30.1% | - | - | - | - | 58.6% | 58.6% |
| nl | 12.5% | 32.9% | 13.4% | 42.3% | 42.3% | - | - | - | - | 49.7% | 49.7% |
| pt | 20.1% | 36.9% | 19.3% | 42.8% | 42.7% | - | - | - | - | 54.3% | 59.8% |
| tr | 15.7% | 35.3% | - | 44.9% | 43.3% | - | - | - | - | 48.8% | 55.6% |
| zh | 20.6% | 27.5% | - | 38.8% | 42.9% | - | - | - | - | 51.2% | 51.2% |

## Best cutoff rate @ 0.6s latency

![Best cutoff rate @ 0.6s latency heatmap](heatmap_best_cutoff_rate_at_0_6s_latency.png)

| Language | LiveKit Turn Detector v1 | LiveKit Turn Detector v1-mini | Deepgram Flux | ultraVAD | SmartTurn v3.2 | AssemblyAI | Soniox | OpenAI GPT Realtime 2 | Cartesia Ink 2 | Gradium | VAD baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ar | 6.9% | 10.3% | - | 12.9% | 13.2% | - | 6.0% | - | - | 14.1% | 14.8% |
| de | 5.7% | 10.7% | 6.9% | 14.9% | 14.2% | 12.3% | 6.1% | - | - | 13.0% | 21.5% |
| en | 4.5% | 12.1% | 9.9% | 11.9% | 14.8% | 14.6% | 5.5% | - | - | 12.6% | 21.7% |
| es | 6.0% | 12.2% | 8.7% | 17.6% | 17.3% | 18.3% | 11.4% | - | - | 15.2% | 24.5% |
| fr | 5.4% | 8.4% | 5.7% | 10.8% | 10.6% | 9.7% | 3.9% | - | - | 8.2% | 18.5% |
| hi | 2.0% | 5.4% | 4.5% | 6.5% | 6.5% | - | 3.4% | - | - | 5.8% | 7.4% |
| id | 8.8% | 17.6% | - | 17.2% | 15.9% | - | 10.1% | - | - | 22.3% | 22.3% |
| it | 7.9% | 14.8% | 12.2% | 15.5% | 15.2% | 13.9% | 7.6% | - | - | 14.3% | 20.6% |
| ja | 1.3% | 9.1% | 12.7% | 3.5% | 11.2% | - | 6.6% | - | - | 13.5% | 17.6% |
| ko | 2.1% | 6.5% | - | 12.0% | 9.7% | - | - | - | - | 15.2% | 15.2% |
| nl | 5.1% | 11.6% | 7.8% | 15.2% | 13.4% | - | 6.0% | - | - | 13.9% | 17.0% |
| pt | 7.3% | 14.4% | 8.8% | 14.5% | 13.1% | 13.1% | 6.0% | - | - | 9.6% | 17.8% |
| tr | 6.9% | 15.2% | - | 18.5% | 17.9% | - | 9.1% | - | - | 16.3% | 21.8% |
| zh | 8.7% | 13.2% | - | 12.8% | 13.2% | - | 8.7% | - | - | 15.5% | 16.3% |

## Best mean latency @ 5% cutoff

![Best mean latency @ 5% cutoff heatmap](heatmap_best_mean_latency_at_5pct_cutoff.png)

| Language | LiveKit Turn Detector v1 | LiveKit Turn Detector v1-mini | Deepgram Flux | ultraVAD | SmartTurn v3.2 | AssemblyAI | Soniox | OpenAI GPT Realtime 2 | Cartesia Ink 2 | Gradium | VAD baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ar | 706 ms | 811 ms | - | 807 ms | 814 ms | - | 713 ms | 873 ms | - | 840 ms | 900 ms |
| de | 672 ms | 947 ms | 826 ms | 864 ms | 963 ms | 907 ms | 768 ms | 982 ms | - | 881 ms | 1100 ms |
| en | 543 ms | 1070 ms | 1151 ms | 899 ms | 1051 ms | 1049 ms | 647 ms | 1143 ms | 1056 ms | 913 ms | 1600 ms |
| es | 642 ms | 926 ms | 820 ms | 986 ms | 980 ms | 1031 ms | 800 ms | 1044 ms | - | 934 ms | 1200 ms |
| fr | 635 ms | 798 ms | 676 ms | 846 ms | 873 ms | 822 ms | 557 ms | 837 ms | - | 750 ms | 1000 ms |
| hi | 454 ms | 624 ms | 583 ms | 616 ms | 639 ms | - | 553 ms | 641 ms | - | 618 ms | 700 ms |
| id | 832 ms | 938 ms | - | 939 ms | 945 ms | - | 952 ms | 982 ms | - | 1042 ms | 1100 ms |
| it | 784 ms | 966 ms | 1022 ms | 1005 ms | 980 ms | 994 ms | 851 ms | 1009 ms | - | 935 ms | 1100 ms |
| ja | 321 ms | 766 ms | 1003 ms | 462 ms | 837 ms | - | 792 ms | 736 ms | - | 903 ms | 1200 ms |
| ko | 324 ms | 712 ms | - | 731 ms | 734 ms | - | 786 ms | 824 ms | - | 830 ms | 900 ms |
| nl | 610 ms | 884 ms | 789 ms | 910 ms | 884 ms | - | 706 ms | 912 ms | - | 913 ms | 1100 ms |
| pt | 702 ms | 897 ms | 766 ms | 849 ms | 836 ms | 858 ms | 702 ms | 888 ms | - | 728 ms | 1000 ms |
| tr | 718 ms | 1080 ms | - | 1075 ms | 1013 ms | - | 913 ms | 1094 ms | - | 1137 ms | 1200 ms |
| zh | 799 ms | 919 ms | - | 926 ms | 959 ms | - | 886 ms | 941 ms | - | 1012 ms | 1100 ms |

## Best mean latency @ 10% cutoff

![Best mean latency @ 10% cutoff heatmap](heatmap_best_mean_latency_at_10pct_cutoff.png)

| Language | LiveKit Turn Detector v1 | LiveKit Turn Detector v1-mini | Deepgram Flux | ultraVAD | SmartTurn v3.2 | AssemblyAI | Soniox | OpenAI GPT Realtime 2 | Cartesia Ink 2 | Gradium | VAD baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ar | 444 ms | 610 ms | - | 654 ms | 636 ms | - | 489 ms | 682 ms | - | 643 ms | 700 ms |
| de | 350 ms | 618 ms | 403 ms | 703 ms | 706 ms | 678 ms | 463 ms | 696 ms | - | 680 ms | 800 ms |
| en | 295 ms | 698 ms | 548 ms | 663 ms | 739 ms | 713 ms | 512 ms | 824 ms | 911 ms | 656 ms | 1000 ms |
| es | 438 ms | 667 ms | 536 ms | 764 ms | 769 ms | 792 ms | 611 ms | 755 ms | - | 709 ms | 1000 ms |
| fr | 376 ms | 541 ms | 353 ms | 613 ms | 608 ms | 598 ms | 463 ms | 652 ms | - | 563 ms | 800 ms |
| hi | 306 ms | 505 ms | 459 ms | 509 ms | 532 ms | - | 553 ms | 641 ms | - | 530 ms | 600 ms |
| id | 555 ms | 770 ms | - | 741 ms | 748 ms | - | 601 ms | 753 ms | - | 783 ms | 800 ms |
| it | 494 ms | 744 ms | 672 ms | 729 ms | 746 ms | 717 ms | 473 ms | 751 ms | - | 696 ms | 900 ms |
| ja | 220 ms | 561 ms | 701 ms | 347 ms | 622 ms | - | 583 ms | 672 ms | - | 671 ms | 900 ms |
| ko | 228 ms | 376 ms | - | 636 ms | 586 ms | - | 615 ms | 668 ms | - | 685 ms | 700 ms |
| nl | 366 ms | 659 ms | 485 ms | 706 ms | 700 ms | - | 451 ms | 743 ms | - | 679 ms | 800 ms |
| pt | 482 ms | 700 ms | 571 ms | 679 ms | 668 ms | 672 ms | 453 ms | 749 ms | - | 596 ms | 800 ms |
| tr | 439 ms | 729 ms | - | 798 ms | 779 ms | - | 584 ms | 877 ms | - | 768 ms | 900 ms |
| zh | 577 ms | 691 ms | - | 688 ms | 679 ms | - | 548 ms | 666 ms | - | 748 ms | 800 ms |
