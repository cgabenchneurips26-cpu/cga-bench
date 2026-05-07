 Contribution 4 "Evaluator Audit Kit" 신뢰도 제고 — 같이 고민                                                                           
                                                                                                                                         
  ▎ 핵심 claim: pi-class가 verdict independence를 예측한다 (τ̄=0.473 within vs 0.192 cross). Descriptive → Predictive로 프레이밍 전환.    
                                                                                                                                         
  reviewer 공격면을 먼저 열거하고, 각각에 대응하는 실험/검증을 tier 로 정리합니다.                                                       
                                                                                                                                         
  Attack surface 10개                                                                                                                    
                                                                                                     
  ┌─────┬───────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────┐   
  │  #  │                             공격                              │                         한 줄 요지                         │
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤   
  │ A1  │ "τ̄ gap 통계적 유의성?"                                        │ 19 evaluator → C(n,2) 약 171 pair. p-value, CI 없으면      │
  │     │                                                               │ noise일 수 있음                                            │
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤   
  │ A2  │ "one-corpus artifact"                                         │ 14,826 episode가 v6 한 corpus. Hold-out 없으면 overfitting │   
  │     │                                                               │  의혹                                                      │   
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤   
  │ A3  │ "pi-class 할당이 post-hoc tune"                               │ 이론으로 분류했다지만 τ̄ 보고 나서 재조정했을 가능성        │
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤   
  │ A4  │ "EVP 2개(VC+LLMJudge)는 toy"                                  │ 외부 scorer 진짜 plug-in 사례가 부족                       │
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤   
  │ A5  │ "BSR/Bayes floor는 data-processing inequality"                │ 이론은 classical, tool은 따로 필요                         │
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤   
  │ A6  │ "correlation ≠ causation within-class"                        │ 같은 class라서 correlate하는 게 아니라, 둘 다 같은         │
  │     │                                                               │ episode에 약할 수도                                        │   
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
  │ A7  │ "Kendall τ 는 crude"                                          │ Spearman, Cohen's κ, MCC 중 다른 지표로도 확인되나?        │   
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
  │ A8  │ "reviewer가 직접 plug-in 해볼 수 없음"                        │ Gradio demo만으론 claim 검증 불충분                        │   
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
  │ A9  │ "drift regression = tool 자체가 fragile"                      │ silent-zero 사고가 신뢰 훼손 근거로 역공 가능              │   
  ├─────┼───────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
  │ A10 │ "self-audit 발견된 결함 (ac_proxy≡acov_shim)은 code review도  │ tool이 없어도 잡을 수 있는 trivial 발견                    │   
  │     │ 잡았을 것"                                                    │                                                            │
  └─────┴───────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────┘

  실험/검증 제안 (effort 기준 tier 분류)                                                                                                 
  
  Tier 0 — 없으면 paper가 약해지는 필수 (합쳐 ~3시간)                                                                                    
                                                                                                     
  1. Permutation test on τ̄ gap (1h)                                                                                                      
    - 10,000 random relabeling of pi-class on 19 evaluators → 재계산한 within-class − cross-class τ̄ gap
    - 관측된 0.473 − 0.192 = 0.281 이 분포의 tail에 속하는지 → permutation p-value                                                       
    - Payoff: A1 directly kill. "p < 0.001" 한 줄이면 끝.                                                                                
  2. Bootstrap 95% CI (30m)                                                                                                              
    - 1,000 bootstrap resample of 14,826 episodes → 재계산 within-class τ̄, cross-class τ̄                                                 
    - 두 CI의 non-overlap 명시                                                                                                           
    - Payoff: A1 보강. paper table에 CI 한 컬럼 추가.                                                                                    
  3. Silent-zero regression을 §4.4.4 로 서사화 (writing 30m)                                                                             
    - "Our harness caught a bug in our own follow-up work" — A9 방어를 공격으로 전환                                                     
    - 3개 bridge가 identical 0.4839 produce → harness τ 매트릭스가 "너무 완벽한 동일성" 이상치 flag → 원인 추적 → 3개 silent bug fix →   
  rerun에 서로 다른 BSR                                                                                                                  
    - Payoff: tool의 practical value 실증. novelty 강화.                                                                                 
                                                                                                                                         
  Tier 1 — credibility 눈에 띄게 올라감 (합쳐 ~5시간)                                                                                    
                                                                                                                                         
  4. Held-out 5 CPG generalization (2h)                                                                                                  
    - ABA Burn / ACOG OB / APA Agitation / PALS / Toxicology 에피소드만으로 τ̄ 재계산                 
    - 이 5개는 core 20에 포함 안 됨 (CLAUDE.md held-out tier) → 진짜 unseen                                                              
    - Within vs cross gap 유지되면 "pi-class predictivity는 corpus-wide artifact 아님"                                                   
    - Payoff: A2 직격                                                                                                                    
  5. Per-domain τ̄ boxplot (1h)                                                                                                           
    - 25개 CPG domain 각각에서 within-class τ̄ 분포                                                                                       
    - Box plot으로 분산 시각화                                                                                                           
    - Payoff: A2 보강, 서사적으로 강력                                                                                                   
  6. Random-clustering null baseline (1h)                                                                                                
    - 19 evaluator를 4 그룹으로 무작위 할당 10,000번 → 그 분포의 within-cluster τ̄ 평균               
    - Pi-class의 0.473이 random partition 상위 1%에 속해야 predictive                                                                    
    - Payoff: A3/A6 직격, "pi-class assignment이 data-driven이 아니고 theoretical이다" 를 empirically 뒷받침                             
  7. Mixed-effects regression (1h)                                                                                                       
    - τ_ij ~ SameClass_ij + (1|evaluator_i) + (1|evaluator_j), restricted MLE                                                            
    - fixed-effect coefficient + p-value 제시                                                                                            
    - Payoff: A1/A7 동시 대응, ICC로 evaluator간 residual 변동 정량화                                                                    
                                                                                                                                         
  Tier 2 — nice-to-have, rebuttal 에서 반격 탄약 (합쳐 ~반나절)                                                                          
                                                                                                                                         
  8. Alt correlation metrics (30m)                                                                                                       
    - Spearman, Pearson, Cohen's κ, Matthews correlation 모두 within > cross 확인                    
    - Paper에는 한 줄 "all four converge"; supplement에 full table                                                                       
    - Payoff: A7 kill                                                                                                                    
  9. Adversarial evaluator pair test (2h)                                                                                                
    - Construct e1 (pi-class=term) + e2 = e1 + noise → expected τ≈1                                                                      
    - Construct e3 with same marginal BSR but crafted pi-class=nctx verdicts → expected τ≈0.19                                           
    - 같은 harness로 자동 분류되는지 확인 → pi-class가 marginal BSR로 환원 안 됨 증명                                                    
    - Payoff: A6 직격                                                                                                                    
  10. Reviewer plug-in UX (user study lite) (반나절)                                                                                     
    - 3–5명 independent contributor에게 MkDocs 튜토리얼만 주고 새 Evaluator subclass 작성 요청                                           
    - (a) 시간 측정 (b) 본인 예측 pi-class vs 자동 분류 결과 일치도                                                                      
    - N=3 이라도 "external annotator가 30분 안에 plug-in 가능, pi-class 일치율 X/Y" 주장 가능                                            
    - Payoff: A4/A8 동시, NeurIPS D&B 심사위원이 제일 원하는 "tool이 실제 extensible" 근거                                               
    - 익명성 주의: MIT 대학원생 같은 specific grouping 은 identity 유추 가능 → "anonymous external contributors" 로만 표기               
  11. EVP를 6개로 확장 (2h)                                                                                                              
    - 현재 VC + LLMJudge 2개 → 외부 bridge (MedAgent, ART, AgentEHR, HealthBench, AMEGA, CliBench) native 가 이미 있음                   
    - 이를 "6개의 third-party evaluator가 harness로 자동 pi-class 분류됨" 으로 재포장                                                    
    - 각 bridge의 theoretically-expected pi-class vs 실제 auto-classified pi-class 일치 테이블                                           
    - Payoff: A4 kill, supplement에 full reproducibility                                                                                 
                                                                                                                                         
  Tier 3 — scope creep 위험 (camera-ready 이후 consider)                                                                                 
                                                                                                                                         
  12. Gradio demo에 "paste your evaluator code" sandbox execution + 30초 audit — 실제로 reviewer가 써볼 수 있게                          
  13. Inter-rater reliability on pi-class assignment: 2명이 독립 분류, Cohen's κ 보고 