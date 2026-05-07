from __future__ import annotations

from dataclasses import asdict

import pytest

from cga_bench.semantic_layer.external.healthbench_dialogue import (
    DialogueAct,
    DialogueActConfig,
    DialogueGraph,
    DialogueState,
    DialogueTransition,
    DialogueTurn,
    build_dialogue_graph,
    classify_dialogue_acts,
    graph_summary,
    parse_conversation_to_turns,
    update_dialogue_state,
)


@pytest.fixture
def sample_conversation() -> list[dict[str, object]]:
    return [
        {"role": "user", "content": "I've been having severe headaches for the past week."},
        {
            "role": "assistant",
            "content": "I'm sorry to hear that. Can you tell me more about the headaches? Are they constant or do they come and go?",
        },
        {
            "role": "user",
            "content": "They come and go, usually worse in the morning. I also feel nauseous.",
        },
        {
            "role": "assistant",
            "content": "Thank you for sharing that. Given the pattern of morning headaches with nausea, I recommend seeing your doctor within the next few days. In the meantime, you can take acetaminophen for pain relief, but avoid exceeding 3000mg daily.",
        },
    ]


@pytest.fixture
def default_config() -> DialogueActConfig:
    return DialogueActConfig.default()


@pytest.fixture
def empty_state() -> DialogueState:
    return DialogueState(
        turn_count=0,
        patient_info={},
        detected_conditions=[],
        current_goal="initial_assessment",
        conversation_summary="",
    )


class TestDialogueActEnum:
    def test_dialogue_act_has_expected_member_count(self) -> None:
        assert len(DialogueAct) == 8

    @pytest.mark.parametrize(
        "member_name",
        [
            "INFORMATION_PROVIDE",
            "QUESTION_ASK",
            "EMPATHY_EXPRESS",
            "TRIAGE_RECOMMEND",
            "INSTRUCTION_GIVE",
            "SAFETY_WARNING",
            "REASSURANCE",
            "CLARIFICATION_REQUEST",
        ],
    )
    def test_dialogue_act_members_exist(self, member_name: str) -> None:
        assert hasattr(DialogueAct, member_name)


class TestDialogueActConfig:
    def test_config_injection_preserves_custom_values(self) -> None:
        config = DialogueActConfig(
            empathy_keywords=["sorry", "understand"],
            safety_keywords=["call 911", "emergency"],
            question_patterns=[r"\?$", r"^what"],
        )

        assert config.empathy_keywords == ["sorry", "understand"]
        assert config.safety_keywords == ["call 911", "emergency"]
        assert config.question_patterns == [r"\?$", r"^what"]

    def test_default_factory_returns_config_instance(self) -> None:
        config = DialogueActConfig.default()
        assert isinstance(config, DialogueActConfig)
        assert isinstance(config.empathy_keywords, list)
        assert isinstance(config.safety_keywords, list)
        assert isinstance(config.question_patterns, list)


class TestDialogueTurnContract:
    def test_dialogue_turn_typed_dict_has_expected_keys(self) -> None:
        expected = {"role", "content", "acts", "turn_index"}
        assert set(DialogueTurn.__annotations__.keys()) == expected

    def test_dialogue_turn_accepts_dialogue_act_list(self) -> None:
        turn: DialogueTurn = {
            "role": "assistant",
            "content": "Please monitor your blood pressure daily.",
            "acts": [DialogueAct.INSTRUCTION_GIVE],
            "turn_index": 1,
        }
        assert turn["acts"] == [DialogueAct.INSTRUCTION_GIVE]


class TestDialogueStateContract:
    def test_dialogue_state_dataclass_fields_exist(self, empty_state: DialogueState) -> None:
        serialized = asdict(empty_state)
        assert set(serialized.keys()) == {
            "turn_count",
            "patient_info",
            "detected_conditions",
            "current_goal",
            "conversation_summary",
        }


class TestClassifyDialogueActs:
    @pytest.mark.parametrize(
        ("utterance", "expected_acts"),
        [
            (
                "I understand your concern. You should take ibuprofen 400mg every 6 hours.",
                {DialogueAct.EMPATHY_EXPRESS, DialogueAct.INSTRUCTION_GIVE},
            ),
            ("What symptoms are you experiencing?", {DialogueAct.QUESTION_ASK}),
            (
                "Call 911 immediately if you experience chest pain",
                {DialogueAct.SAFETY_WARNING, DialogueAct.TRIAGE_RECOMMEND},
            ),
            (
                "Your blood test results are normal.",
                {DialogueAct.INFORMATION_PROVIDE, DialogueAct.REASSURANCE},
            ),
        ],
    )
    def test_classify_expected_multi_label_cases(
        self,
        utterance: str,
        expected_acts: set[DialogueAct],
        default_config: DialogueActConfig,
    ) -> None:
        acts = classify_dialogue_acts(utterance, default_config)
        assert expected_acts.issubset(set(acts))

    def test_classify_empty_utterance_returns_empty_list(self, default_config: DialogueActConfig) -> None:
        assert classify_dialogue_acts("", default_config) == []

    def test_classify_very_short_utterance_returns_empty_list(self, default_config: DialogueActConfig) -> None:
        assert classify_dialogue_acts("hmm", default_config) == []


class TestUpdateDialogueState:
    def test_update_returns_new_state_without_mutating_original(
        self,
        empty_state: DialogueState,
    ) -> None:
        turn: DialogueTurn = {
            "role": "user",
            "content": "I have diabetes and hypertension.",
            "acts": [DialogueAct.INFORMATION_PROVIDE],
            "turn_index": 0,
        }

        updated = update_dialogue_state(empty_state, turn)

        assert updated is not empty_state
        assert empty_state.turn_count == 0
        assert updated.turn_count == 1

    def test_update_extracts_detected_conditions(self, empty_state: DialogueState) -> None:
        turn: DialogueTurn = {
            "role": "user",
            "content": "My history includes diabetes and hypertension.",
            "acts": [DialogueAct.INFORMATION_PROVIDE],
            "turn_index": 0,
        }

        updated = update_dialogue_state(empty_state, turn)

        lowered = {condition.lower() for condition in updated.detected_conditions}
        assert "diabetes" in lowered
        assert "hypertension" in lowered

    def test_update_adds_patient_info_from_content(self, empty_state: DialogueState) -> None:
        turn: DialogueTurn = {
            "role": "user",
            "content": "Age: 54, symptom: headache",
            "acts": [DialogueAct.INFORMATION_PROVIDE],
            "turn_index": 0,
        }

        updated = update_dialogue_state(empty_state, turn)

        assert isinstance(updated.patient_info, dict)
        assert len(updated.patient_info) >= 1


class TestParseConversationToTurns:
    def test_parse_empty_input_returns_empty_list(self, default_config: DialogueActConfig) -> None:
        assert parse_conversation_to_turns([], default_config) == []

    def test_parse_single_turn_returns_one_turn(self, default_config: DialogueActConfig) -> None:
        turns = parse_conversation_to_turns(
            [{"role": "user", "content": "What should I do for fever?"}],
            default_config,
        )
        assert len(turns) == 1
        assert turns[0]["role"] == "user"
        assert turns[0]["turn_index"] == 0

    def test_parse_includes_system_messages(self, default_config: DialogueActConfig) -> None:
        prompt_turns: list[dict[str, object]] = [
            {"role": "system", "content": "You are a safe clinical assistant."},
            {"role": "user", "content": "I have chest pain."},
        ]

        turns = parse_conversation_to_turns(prompt_turns, default_config)

        assert len(turns) == 2
        assert turns[0]["role"] == "system"
        assert turns[1]["role"] == "user"

    def test_parse_multi_turn_classifies_each_turn(
        self,
        sample_conversation: list[dict[str, object]],
        default_config: DialogueActConfig,
    ) -> None:
        turns = parse_conversation_to_turns(sample_conversation, default_config)

        assert len(turns) == len(sample_conversation)
        assert [turn["turn_index"] for turn in turns] == [0, 1, 2, 3]
        assert all(isinstance(turn["acts"], list) for turn in turns)
        assert any(DialogueAct.QUESTION_ASK in turn["acts"] for turn in turns)
        assert any(DialogueAct.INSTRUCTION_GIVE in turn["acts"] for turn in turns)


class TestDialogueTransition:
    def test_transition_typed_dict_keys(self) -> None:
        expected = {"from_goal", "to_goal", "trigger_act", "turn_index"}
        assert set(DialogueTransition.__annotations__.keys()) == expected


class TestDialogueGraph:
    def test_empty_graph_has_initial_node(self) -> None:
        graph = DialogueGraph.empty()
        assert graph.current_node == "initial_assessment"
        assert "initial_assessment" in graph.nodes
        assert len(graph.edges) == 0

    def test_add_transition_returns_new_graph(self) -> None:
        graph = DialogueGraph.empty()
        graph2 = graph.add_transition("information_gathering", "question_ask", 0)
        assert graph2 is not graph
        assert len(graph2.edges) == 1
        assert graph2.current_node == "information_gathering"
        assert len(graph.edges) == 0

    def test_visit_counts_track_state_visits(self) -> None:
        graph = DialogueGraph.empty()
        graph = graph.add_transition("information_gathering", "question_ask", 0)
        graph = graph.add_transition("rapport_building", "empathy_express", 1)
        graph = graph.add_transition("information_gathering", "question_ask", 2)
        assert graph.visit_counts["information_gathering"] == 2
        assert graph.visit_counts["rapport_building"] == 1


class TestBuildDialogueGraph:
    def test_builds_from_sample_conversation(
        self,
        sample_conversation: list[dict[str, object]],
        default_config: DialogueActConfig,
    ) -> None:
        turns = parse_conversation_to_turns(sample_conversation, default_config)
        graph = build_dialogue_graph(turns, default_config)
        assert len(graph.nodes) >= 2
        assert len(graph.edges) >= 1

    def test_empty_turns_returns_empty_graph(self, default_config: DialogueActConfig) -> None:
        graph = build_dialogue_graph([], default_config)
        assert graph.current_node == "initial_assessment"
        assert len(graph.edges) == 0

    def test_build_uses_classifier_when_acts_missing(self, default_config: DialogueActConfig) -> None:
        turns: list[DialogueTurn] = [
            {
                "role": "assistant",
                "content": "Can you tell me more about your symptoms?",
                "acts": [],
                "turn_index": 0,
            }
        ]
        graph = build_dialogue_graph(turns, default_config)
        assert graph.current_node == "information_gathering"
        assert graph.edges[0]["trigger_act"] == DialogueAct.QUESTION_ASK.value

    def test_build_only_adds_edges_on_state_change(self, default_config: DialogueActConfig) -> None:
        turns: list[DialogueTurn] = [
            {
                "role": "assistant",
                "content": "What symptoms are you experiencing?",
                "acts": [DialogueAct.QUESTION_ASK],
                "turn_index": 0,
            },
            {
                "role": "assistant",
                "content": "When did this begin?",
                "acts": [DialogueAct.QUESTION_ASK],
                "turn_index": 1,
            },
        ]
        graph = build_dialogue_graph(turns, default_config)
        assert len(graph.edges) == 1
        assert graph.current_node == "information_gathering"


class TestGraphSummary:
    def test_summary_has_expected_keys(
        self,
        sample_conversation: list[dict[str, object]],
        default_config: DialogueActConfig,
    ) -> None:
        turns = parse_conversation_to_turns(sample_conversation, default_config)
        graph = build_dialogue_graph(turns, default_config)
        summary = graph_summary(graph)
        assert "total_nodes" in summary
        assert "total_edges" in summary
        assert "visit_counts" in summary
        assert "current_state" in summary
        assert "transition_sequence" in summary

    def test_summary_edge_count_matches_graph(
        self,
        sample_conversation: list[dict[str, object]],
        default_config: DialogueActConfig,
    ) -> None:
        turns = parse_conversation_to_turns(sample_conversation, default_config)
        graph = build_dialogue_graph(turns, default_config)
        summary = graph_summary(graph)
        assert summary["total_edges"] == len(graph.edges)

    def test_summary_transition_sequence_matches_edge_targets(self, default_config: DialogueActConfig) -> None:
        turns: list[DialogueTurn] = [
            {
                "role": "assistant",
                "content": "What symptoms are you experiencing?",
                "acts": [DialogueAct.QUESTION_ASK],
                "turn_index": 0,
            },
            {
                "role": "assistant",
                "content": "I recommend seeing your doctor urgently.",
                "acts": [DialogueAct.TRIAGE_RECOMMEND],
                "turn_index": 1,
            },
        ]
        graph = build_dialogue_graph(turns, default_config)
        summary = graph_summary(graph)
        assert summary["transition_sequence"] == ["information_gathering", "triage"]
