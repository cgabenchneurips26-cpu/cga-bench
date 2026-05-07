"""
CGA-Bench: Clinical Guideline Adherence Benchmark

LLM 에이전트가 임상 가이드라인(CPG)의 시간 제약이 있는
치료 프로토콜을 얼마나 잘 준수하는지 평가하는 벤치마크입니다.

핵심 구성요소:
- cpg_model: 가이드라인 그래프 및 스키마 정의
- cpg_engine: 가이드라인 실행 엔진 (채점 전용)
- scenario_engine: 임상 시뮬레이션 환경
- tool_api: 에이전트 도구 인터페이스
- agent_runner: 에이전트 실행기
- agent_rules: 에이전트 독립 규칙 시스템
- assessor_core: 위반 추출 및 점수 계산 (채점 전용)
- eval_harness: 평가 하니스
"""

__version__ = "0.2.0"
__author__ = "CGA-Bench Team"
