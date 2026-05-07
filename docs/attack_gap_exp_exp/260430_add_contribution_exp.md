5. 추가 실험은 “큰 실험”이 아니라 3개의 작은 방어 실험이면 충분합니다
5.1 반드시 추천: E12 Authority Threshold Sweep

E9에서 가장 공격받을 지점은 high-authority taxonomy입니다. 현재 high-authority 정의는 AHA Class I/IIa with LOE A/B, IDSA Strong, KDIGO/AABB strong, GRADE 1A/1B, drug-allergy contraindications입니다. 이건 합리적이지만 reviewer는 “IIa+B까지 high-authority로 넣은 게 너무 넓다”고 할 수 있습니다. E9 report도 taxonomy sensitivity를 optional sweep으로 제안합니다.

따라서 다음 3개 sweep만 추가하면 됩니다.

Sweep	목적	예상 사용처
S1: current high-authority	현재 E9 headline	main §5.5
S2: strictest authority: Class I + LOE A, GRADE 1A, Strong/high only	taxonomy가 넓다는 공격 방어	appendix
S3: no-allergy-injection	drug-allergy를 all high-authority로 둔 결정 방어	appendix

성공 기준은 “숫자가 동일해야 한다”가 아닙니다. 다음 정도면 충분합니다.

strictest filter에서도 strict FA가 non-zero이고, replay detection loss가 qualitative하게 유지되며, projection ordering이 유지된다.

이 sweep은 새 model inference가 아니라 audit-side filter 변경이므로 비용이 작습니다. E9 report 기준으로 script가 약 3분에 돈다면, taxonomy 3회 sweep은 반나절 안에 정리 가능합니다.

5.2 강력 추천: node-level authority spot-check

E9 limitation 중 하나가 “authority extracted at node level, not edge level”입니다. 이건 reviewer가 정확히 칠 수 있습니다. schema를 바꾸는 큰 작업은 필요 없습니다. 대신 spot-check를 합니다.

추천 설계는 간단합니다.

strict false-accept 1,124개 중 60개를 stratified sample로 뽑고, responsible violation edge의 source recommendation / class / LOE가 node-level authority와 일치하는지 수동 확인.

결과가 좋으면 appendix에 한 문장만 넣으면 됩니다.

A manual spot-check of 60 strict-FA episodes found no case in which node-level authority promoted a low-authority edge into the high-authority subset.

이건 E9의 가장 현실적인 약점을 막습니다. clinician validation보다 훨씬 작고, 지금 당장 가능한 방어 실험입니다.

5.3 선택 추천: E10 Severity Overlay

E9가 “high-authority”를 보여줬다면, reviewer의 다음 질문은 “그럼 harm severity도 높은가?”입니다. 이미 현재 appendix에는 severity composition이 있고, consensus false-accept 중 critical severity가 22.1%라는 식의 severity breakdown이 있습니다.

따라서 새 실험이라기보다 overlay입니다.

high-authority strict-FA 1,124개를 severity별로 stratify해서 critical/high/medium share를 보고한다.

이 결과가 좋으면 E9가 한 단계 더 강해집니다.

The high-authority blind spot is not only guideline-authoritative but also harm-relevant.

단, 이건 결과가 좋을 때만 main에 넣고, 애매하면 appendix로 내리면 됩니다. E9만으로도 충분히 강합니다.