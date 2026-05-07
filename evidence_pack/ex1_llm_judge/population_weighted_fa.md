# EX-1 Population-Weighted FA (P1 strict prompt)

Sample: 340 TCC-fail + 160 TCC-pass per level/prompt
Population: ~74.7% TCC-fail, ~25.3% TCC-pass

| Level | Raw FA | Pop-weighted FA | P(pass\|fail) | P(pass\|pass) |
|-------|--------|-----------------|---------------|---------------|
| T0 | 0.4% | 0.4% | 0.6% | 0.0% |
| T1 | 16.8% | 18.5% | 24.7% | 21.9% |
| T2 | 21.8% | 23.9% | 32.1% | 32.5% |
| T3 | 4.4% | 4.8% | 6.5% | 6.2% |

T2→T3 gap (pop-weighted): 19.1pp
BSR_cond at T2: 32.1% (1 in 3 TCC-fail episodes are false-accepted)
BSR_cond at T3: 6.5% (trace reduces false-acceptance 5x)
