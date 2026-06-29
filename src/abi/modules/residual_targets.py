"""Controller-owned residual target specifications and adapters."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from abi.hashing import sha256_text
from abi.model_schemas import (
    OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA,
    RESIDUAL_INTERVENTION_GENERATION_SCHEMA,
    WorkerRole,
    WorkerSchema,
)


OBJECT_MOTION_CAUSALITY_TARGET_ID = "object_motion_causality_specificity"
TACTILE_INEVITABILITY_TARGET_ID = "tactile_inevitability_gap"
HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID = "hostile_scaffold_visibility"
REPEATED_BROAD_TARGET_ID = "first_read_object_event_pressure_gap"
SELECTED_REGION_ID = "middle_recurrence_ordinary_trace_logic"
OBJECT_MOTION_TARGET_SPEC_VERSION = "1"
TACTILE_TARGET_SPEC_VERSION = "2"
HOSTILE_SCAFFOLD_TARGET_SPEC_VERSION = "1"
OBJECT_MOTION_WORK_ORDER_CONTRACT_VERSION = "1"
TACTILE_WORK_ORDER_CONTRACT_VERSION = "2"
HOSTILE_SCAFFOLD_WORK_ORDER_CONTRACT_VERSION = "1"
OBJECT_MOTION_GENERATION_CONTRACT_VERSION = "1"
TACTILE_GENERATION_CONTRACT_VERSION = "1"
HOSTILE_SCAFFOLD_GENERATION_CONTRACT_VERSION = "1"
PLACEHOLDER_GENERATION_CONTRACT_VERSIONS = ("placeholder_1",)
HOSTILE_SCAFFOLD_PLACEHOLDER_MATERIALITY_POLICY_ID = (
    "hostile_scaffold_visibility_planning_placeholder_v1"
)
HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID = (
    "hostile_scaffold_visibility_generation_materiality_v1"
)
PLACEHOLDER_MATERIALITY_POLICY_IDS = (
    HOSTILE_SCAFFOLD_PLACEHOLDER_MATERIALITY_POLICY_ID,
)


@dataclass(frozen=True)
class ResidualTargetSpec:
    target_id: str
    canonical_next_action: str
    review_action: str
    work_order_adapter: str
    mechanism_description: str
    permitted_source_candidate_kinds: tuple[str, ...]
    required_evidence_inputs: tuple[str, ...]
    generation_requires_separate_authorization: bool
    target_specific_ablation_controls: tuple[str, ...]
    target_specific_reader_state_focus: tuple[str, ...]
    target_definition: dict[str, bool]
    operational_definition: tuple[str, ...]
    forbidden_under_this_target: tuple[str, ...]
    protected_effects: tuple[str, ...]
    forbidden_changes: tuple[str, ...]


@dataclass(frozen=True)
class ResidualMaterialityPolicy:
    policy_id: str
    policy_version: str
    primary_materiality_scope: str
    whole_region_guard: dict[str, object]
    target_bearing_scope: dict[str, object]
    target_unit_scope: dict[str, object]
    overlap_cluster_policy: dict[str, object]
    absolute_change_floor: int
    ratio_floor: float
    token_edit_distance_floor: int
    sequence_similarity_ceiling: float
    changed_sentence_floor: int
    protected_context_exemptions: tuple[str, ...]
    prompt_feedback: tuple[str, ...]
    failure_report_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "primary_materiality_scope": self.primary_materiality_scope,
            "whole_region_guard": dict(self.whole_region_guard),
            "target_bearing_scope": dict(self.target_bearing_scope),
            "target_unit_scope": dict(self.target_unit_scope),
            "overlap_cluster_policy": dict(self.overlap_cluster_policy),
            "absolute_change_floor": self.absolute_change_floor,
            "ratio_floor": self.ratio_floor,
            "token_edit_distance_floor": self.token_edit_distance_floor,
            "sequence_similarity_ceiling": self.sequence_similarity_ceiling,
            "changed_sentence_floor": self.changed_sentence_floor,
            "protected_context_exemptions": list(self.protected_context_exemptions),
            "prompt_feedback": list(self.prompt_feedback),
            "failure_report_fields": list(self.failure_report_fields),
        }


@dataclass(frozen=True)
class ResidualTargetAdapter:
    target_id: str
    target_spec_version: str
    work_order_contract_version: str
    generation_contract_version: str
    canonical_work_order_action: str
    review_action: str
    work_order_adapter: str
    generation_schema: WorkerSchema
    worker_role: WorkerRole
    prompt_contract_id: str
    prompt_instructions: tuple[str, ...]
    mechanism_contract: tuple[str, ...]
    ablation_controls: tuple[str, ...]
    reader_state_evaluation_focus: tuple[str, ...]
    stop_test_policy: dict[str, object]
    materiality_policy: ResidualMaterialityPolicy

    @property
    def adapter_id(self) -> str:
        return self.work_order_adapter


OBJECT_MOTION_SPEC = ResidualTargetSpec(
    target_id=OBJECT_MOTION_CAUSALITY_TARGET_ID,
    canonical_next_action="prepare_object_motion_causality_specificity_work_order",
    review_action="review_object_motion_causality_work_order_before_generation_authorization",
    work_order_adapter="object_motion_causality",
    mechanism_description=(
        "A moved, therefore B visibly changed before explanation names the relation."
    ),
    permitted_source_candidate_kinds=("bounded_macro_recomposition",),
    required_evidence_inputs=(
        "current best candidate text",
        "strategy residual target option map",
        "strategy candidate region pressure map",
        "proof packet reference",
        "reader-state packet reference",
    ),
    generation_requires_separate_authorization=True,
    target_specific_ablation_controls=(
        "revert_object_motion_causality_intervention",
        "isolate_object_motion_relation",
        "decorative_vividness_control",
        "object_list_no_causal_motion_control",
        "strongest_rival_comparison",
    ),
    target_specific_reader_state_focus=(
        "first-read causal specificity",
        "object movement producing consequence before explanation",
        "reread preservation",
        "proof/no-answer carry",
        "final-return preservation",
        "hostile scaffold risk",
    ),
    target_definition={
        "object_movement_should_produce_visible_consequence_before_explanation": True,
        "object_relation_should_sharpen_causal_pressure": True,
        "reader_should_infer_pressure_locally": True,
        "must_preserve_current_best_macro_and_reader_state_gains": True,
    },
    operational_definition=(
        "object movement should produce visible consequence before explanation",
        "object relation should sharpen causal pressure",
        "the intervention should make the reader infer pressure locally",
        "the intervention must preserve current-best macro and reader-state gains",
    ),
    forbidden_under_this_target=(
        "generic vividness",
        "object lists",
        "decorative sensory detail",
        "rival mimicry",
        "proof/no-answer compression by inertia",
        "final-return overwork",
        "summary compression",
        "abstract explanation of causality",
        "direct candidate generation in this command",
    ),
    protected_effects=(
        "current best candidate",
        "executed ablation support",
        "reader-state support",
        "partial reread transformation",
        "existing record-bearing object field",
        "proof/no-answer gains",
        "final-return gains",
        "reduced overexplanation",
        "current macro structure",
        "strongest-rival pressure preservation",
        "no finality claim",
    ),
    forbidden_changes=(
        "add decorative vividness",
        "mimic rival",
        "generic vividness",
        "object lists",
        "decorative sensory detail",
        "rival mimicry",
        "proof/no-answer compression by inertia",
        "final-return overwork",
        "summary compression",
        "abstract explanation of causality",
        "candidate generation in this command",
        "finality claim",
        "phase-shift claim",
    ),
)

TACTILE_INEVITABILITY_SPEC = ResidualTargetSpec(
    target_id=TACTILE_INEVITABILITY_TARGET_ID,
    canonical_next_action="prepare_tactile_inevitability_work_order",
    review_action="review_tactile_inevitability_work_order_before_generation_authorization",
    work_order_adapter="tactile_inevitability",
    mechanism_description=(
        "A material force or contact relation makes the change feel physically "
        "unavoidable and non-optional on first encounter."
    ),
    permitted_source_candidate_kinds=("bounded_macro_recomposition",),
    required_evidence_inputs=(
        "current best candidate text",
        "source object-motion work order or candidate text unit evidence",
        "strategy residual target option map",
        "strategy candidate region pressure map",
        "proof packet reference",
        "reader-state packet reference",
    ),
    generation_requires_separate_authorization=True,
    target_specific_ablation_controls=(
        "full_tactile_intervention",
        "revert_tactile_intervention_to_current_best",
        "preserve_object_motion_remove_tactile_force_relation",
        "decorative_sensory_detail_control",
        "abstract_explanation_control",
        "strongest_rival_comparison",
    ),
    target_specific_reader_state_focus=(
        "first-read physical inevitability",
        "material consequence felt before explanation",
        "local embodied force",
        "preservation of current-best reread gains",
        "proof/no-answer carry",
        "return structure preservation",
        "decorative busyness risk",
        "strongest-rival status",
    ),
    target_definition={
        "material_force_or_contact_relation_must_drive_visible_consequence": True,
        "physical_unavoidability_must_be_felt_before_explanation": True,
        "not_generic_vividness_or_more_objects": True,
        "distinct_from_object_motion_causality": True,
        "must_preserve_current_best_macro_and_reader_state_gains": True,
    },
    operational_definition=(
        "contact, weight, pressure, resistance, friction, residue, displacement, "
        "breakage, or another material force must produce visible consequence",
        "the relation should feel physically unavoidable before interpretation explains it",
        "do not add sensory adjectives, new objects, or general vividness",
        "do not repeat object-motion causality; preserve it while adding tactile necessity",
        "the intervention must preserve current-best macro and reader-state gains",
    ),
    forbidden_under_this_target=(
        "decorative sensory detail",
        "new object inventory",
        "rival mimicry",
        "generic vividness amplification",
        "abstract inevitability language",
        "object-motion causality relabeling",
        "full rewrite",
        "reopening unrelated regions",
        "weakening current causal object relations",
        "direct candidate generation in this command",
    ),
    protected_effects=(
        "current best candidate",
        "current-best partial reread transformation",
        "existing record-bearing object field",
        "proof/no-outside-answer gains",
        "opening-return/final-return gains",
        "reduced overexplanation",
        "current macro structure",
        "strongest-rival pressure preservation",
        "no finality claim",
    ),
    forbidden_changes=(
        "decorative sensory detail",
        "new object inventory",
        "rival mimicry",
        "generic vividness amplification",
        "abstract inevitability language",
        "full rewrite",
        "reopening unrelated regions",
        "weakening current causal object relations",
        "candidate generation in this command",
        "finality claim",
        "phase-shift claim",
    ),
)

HOSTILE_SCAFFOLD_VISIBILITY_SPEC = ResidualTargetSpec(
    target_id=HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    canonical_next_action="prepare_hostile_scaffold_visibility_work_order",
    review_action="review_hostile_scaffold_visibility_work_order_before_generation_authorization",
    work_order_adapter="hostile_scaffold_visibility",
    mechanism_description=(
        "Reduce visible thesis/scaffold/explanatory pressure while preserving "
        "the embodied causal object field and current reread/proof gains."
    ),
    permitted_source_candidate_kinds=("bounded_macro_recomposition",),
    required_evidence_inputs=(
        "current best candidate text",
        "strategy residual target option map",
        "strategy candidate region pressure map",
        "proof packet reference",
        "reader-state packet reference",
        "synthesis blocker evidence",
        "hostile reader risk evidence",
    ),
    generation_requires_separate_authorization=True,
    target_specific_ablation_controls=(
        "revert_hostile_scaffold_visibility_intervention",
        "isolate_scaffold_reduction_intervention",
        "proof_no_answer_preservation_control",
        "embodiment_preservation_control",
        "strongest_rival_comparison",
    ),
    target_specific_reader_state_focus=(
        "hostile scaffold visibility",
        "thesis replacing artifact risk",
        "overexplanation reduction without vagueness",
        "proof/no-answer carry preservation",
        "opening-return preservation",
        "first-read local embodiment versus compression",
        "strongest-rival pressure",
    ),
    target_definition={
        "visible_thesis_scaffold_or_explanatory_pressure_should_decrease": True,
        "object_field_must_keep_doing_causal_work": True,
        "proof_no_answer_structure_must_be_preserved_as_pressure_not_deleted": True,
        "reader_should_infer_meaning_from_field_before_explanation": True,
        "must_preserve_current_best_macro_and_reader_state_gains": True,
    },
    operational_definition=(
        "reduce visible thesis/scaffold/explanatory framing that tells the reader what the object field means",
        "preserve embodied causal field, tactile/object pressure, proof/no-answer carry, and opening-return/reread gains",
        "keep proof/no-answer pressure embodied rather than deleting or abstracting it",
        "do not return to object-motion or tactile-force microtargeting",
        "do not imitate the rival or add decorative vividness",
        "the intervention must preserve current-best macro and reader-state gains",
    ),
    forbidden_under_this_target=(
        "delete proof/no-answer structure",
        "flatten the artifact into summary",
        "make prose vaguer",
        "add decorative vividness",
        "rival mimicry",
        "weaken the current causal object field",
        "return to object-motion microtargeting",
        "return to tactile-force microtargeting",
        "proof/no-answer abstract explanation",
        "broad rewrite",
        "direct candidate generation in this command",
        "finality claim",
        "phase-shift claim",
    ),
    protected_effects=(
        "current best candidate",
        "executed ablation support",
        "reader-state support",
        "current-best partial reread transformation",
        "tactile/object field gains",
        "table/dust/spoon/saucer/ring causal field",
        "proof/no-answer pressure",
        "opening-return relation",
        "strongest-rival pressure preservation",
        "no finality claim",
        "no phase-shift claim",
    ),
    forbidden_changes=(
        "generic vividness",
        "rival imitation",
        "deleting causal objects",
        "making proof more abstract",
        "summary compression",
        "weakening tactile/object pressure",
        "turning the candidate into explanation",
        "broad rewrite",
        "candidate generation in this command",
        "finality claim",
        "phase-shift claim",
    ),
)

RESIDUAL_TARGET_SPECS = {
    OBJECT_MOTION_SPEC.target_id: OBJECT_MOTION_SPEC,
    TACTILE_INEVITABILITY_SPEC.target_id: TACTILE_INEVITABILITY_SPEC,
    HOSTILE_SCAFFOLD_VISIBILITY_SPEC.target_id: HOSTILE_SCAFFOLD_VISIBILITY_SPEC,
}

MATERIALITY_FAILURE_REPORT_FIELDS = (
    "whole_region_guard_failures",
    "target_bearing_materiality_failures",
    "target_unit_materiality_failures",
    "overlap_cluster_failures",
    "tactile_semantic_failures",
    "object_motion_relabel_failures",
    "generic_decorative_vividness_failures",
    "abstract_inevitability_failures",
    "protected_context_scope_failures",
)

OBJECT_MOTION_MATERIALITY_POLICY = ResidualMaterialityPolicy(
    policy_id="object_motion_selected_region_materiality_v1",
    policy_version="1",
    primary_materiality_scope="whole_selected_region",
    whole_region_guard={
        "scope": "whole_selected_region",
        "enforce_primary_thresholds": True,
        "exact_copy_fails": True,
        "selected_region_copy_fails": True,
    },
    target_bearing_scope={
        "scope": "selected_region",
        "diagnostic_only": True,
    },
    target_unit_scope={
        "scope": "target_unit",
        "diagnostic_only": True,
    },
    overlap_cluster_policy={
        "detect_shared_before_text_hash": True,
        "diagnostic_only": True,
    },
    absolute_change_floor=10,
    ratio_floor=0.12,
    token_edit_distance_floor=1,
    sequence_similarity_ceiling=0.98,
    changed_sentence_floor=1,
    protected_context_exemptions=(
        "none; legacy object-motion generation uses whole selected region as primary denominator",
    ),
    prompt_feedback=(
        "selected-region materiality is required",
        "lexical substitutions are insufficient",
        "target-unit mappings are necessary but insufficient",
        "preserve protected effects rather than exact sentence architecture",
    ),
    failure_report_fields=MATERIALITY_FAILURE_REPORT_FIELDS,
)

TACTILE_MATERIALITY_POLICY = ResidualMaterialityPolicy(
    policy_id="tactile_inevitability_target_bearing_materiality_v1",
    policy_version="1",
    primary_materiality_scope="target_bearing_scope",
    whole_region_guard={
        "scope": "whole_selected_region",
        "near_copy_guard_only": True,
        "exact_copy_fails": True,
        "selected_region_copy_fails": True,
        "do_not_enforce_global_ratio_floor": True,
        "token_edit_distance_floor": 12,
        "sequence_similarity_ceiling": 0.97,
    },
    target_bearing_scope={
        "scope": "paragraph_or_sentence_cluster_containing_target_units",
        "absolute_change_floor": 8,
        "ratio_floor": 0.12,
        "token_edit_distance_floor": 12,
        "sequence_similarity_ceiling": 0.90,
        "changed_sentence_floor": 2,
    },
    target_unit_scope={
        "scope": "each_required_target_unit",
        "absolute_change_floor": 4,
        "ratio_floor": 0.18,
        "token_edit_distance_floor": 5,
        "sequence_similarity_ceiling": 0.86,
        "changed_sentence_floor": 1,
    },
    overlap_cluster_policy={
        "detect_shared_before_text_hash": True,
        "evaluate_integrated_replacement_once": True,
        "validate_member_semantics_separately": True,
        "require_coherent_replacement_not_duplicate_rewrites": True,
    },
    absolute_change_floor=8,
    ratio_floor=0.12,
    token_edit_distance_floor=12,
    sequence_similarity_ceiling=0.90,
    changed_sentence_floor=2,
    protected_context_exemptions=(
        "untargeted protected context may remain stable",
        "do not rewrite healthy context merely to increase a whole-region ratio",
        "preserve effect and function rather than exact target sentence architecture",
    ),
    prompt_feedback=(
        "lexical tightening is insufficient",
        "preserving exact target sentence architecture is insufficient",
        "materially re-author every required tactile unit",
        "surrounding untargeted context may remain stable",
        "do not rewrite protected context merely to raise a global ratio",
        "tactile necessity is distinct from object motion",
    ),
    failure_report_fields=MATERIALITY_FAILURE_REPORT_FIELDS,
)

HOSTILE_SCAFFOLD_MATERIALITY_POLICY = ResidualMaterialityPolicy(
    policy_id=HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID,
    policy_version="1",
    primary_materiality_scope="target_bearing_scope",
    whole_region_guard={
        "scope": "whole_selected_region",
        "near_copy_guard_only": True,
        "exact_copy_fails": True,
        "selected_region_copy_fails": True,
        "do_not_enforce_global_ratio_floor": True,
        "token_edit_distance_floor": 12,
        "sequence_similarity_ceiling": 0.96,
    },
    target_bearing_scope={
        "scope": "selected-region paragraphs containing hostile scaffold target units",
        "absolute_change_floor": 8,
        "ratio_floor": 0.10,
        "token_edit_distance_floor": 12,
        "sequence_similarity_ceiling": 0.91,
        "changed_sentence_floor": 2,
        "must_reduce_visible_scaffold_pressure": True,
        "must_preserve_embodied_object_field": True,
    },
    target_unit_scope={
        "scope": "each hostile scaffold visibility target unit",
        "must_reduce_scaffold_without_deleting_pressure": True,
        "absolute_change_floor": 3,
        "ratio_floor": 0.08,
        "token_edit_distance_floor": 4,
        "sequence_similarity_ceiling": 0.90,
        "changed_sentence_floor": 1,
    },
    overlap_cluster_policy={
        "detect_shared_before_text_hash": True,
        "evaluate_scaffold_reduction_and_embodiment_preservation_together": True,
        "evaluate_integrated_replacement_once": True,
        "validate_member_semantics_separately": True,
        "require_coherent_replacement_not_duplicate_rewrites": True,
    },
    absolute_change_floor=8,
    ratio_floor=0.10,
    token_edit_distance_floor=12,
    sequence_similarity_ceiling=0.91,
    changed_sentence_floor=2,
    protected_context_exemptions=(
        "proof/no-answer pressure outside the selected region is protected and must not be deleted",
        "opening-return and final-return gains outside the selected region are protected references",
        "table/dust/spoon/saucer/ring object field must remain causally active",
    ),
    prompt_feedback=(
        "do not perform a broad rewrite",
        "lexical tightening is insufficient",
        "one-word substitutions are insufficient",
        "preserving target sentence architecture is insufficient",
        "reduce visible explanation rather than deleting proof/no-answer pressure",
        "make the object field carry more of the meaning",
        "materially address all five target units inside the selected region",
        "every hostile-scaffold target unit must be materially re-authored",
        "target-bearing selected region must clear the active materiality policy",
        "do not replace one visible thesis with another",
        "avoid colon-led thesis sentences that announce what the objects mean",
        "do not reuse one long object-list sentence as the answer to multiple target units",
        "abstract pressure labels are not sufficient hostile-scaffold reduction",
        "preserve packet_0063 tactile/object gains",
        "preserve protected references outside the selected region",
        "surrounding protected context may remain stable",
        "do not replace scaffold with vagueness, summary, rival mimicry, or decorative vividness",
    ),
    failure_report_fields=(
        "target_bearing_selected_region_materiality_failures",
        "scaffold_leakage_failures",
        "proof_no_answer_deletion_failures",
        "object_field_preservation_failures",
        "tactile_object_pressure_preservation_failures",
        "vagueness_or_summary_failures",
        "decorative_vividness_failures",
        "rival_mimicry_failures",
        "finality_or_phase_shift_claim_failures",
    ),
)

OBJECT_MOTION_ADAPTER = ResidualTargetAdapter(
    target_id=OBJECT_MOTION_CAUSALITY_TARGET_ID,
    target_spec_version=OBJECT_MOTION_TARGET_SPEC_VERSION,
    work_order_contract_version=OBJECT_MOTION_WORK_ORDER_CONTRACT_VERSION,
    generation_contract_version=OBJECT_MOTION_GENERATION_CONTRACT_VERSION,
    canonical_work_order_action=OBJECT_MOTION_SPEC.canonical_next_action,
    review_action=OBJECT_MOTION_SPEC.review_action,
    work_order_adapter=OBJECT_MOTION_SPEC.work_order_adapter,
    generation_schema=OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA,
    worker_role=WorkerRole.OBJECT_MOTION_CAUSALITY_GENERATOR,
    prompt_contract_id="autonomous.object_motion_causality_generation.v1",
    prompt_instructions=(
        "replace only the selected region",
        "make object movement or state change produce visible consequence before explanation",
        "preserve protected macro and reread gains",
        "avoid decorative vividness, new object lists, rival mimicry, full rewrite, and claims",
    ),
    mechanism_contract=OBJECT_MOTION_SPEC.operational_definition,
    ablation_controls=OBJECT_MOTION_SPEC.target_specific_ablation_controls,
    reader_state_evaluation_focus=OBJECT_MOTION_SPEC.target_specific_reader_state_focus,
    stop_test_policy={
        "cycle_kind": "residual_stop_test",
        "pause_action": "pause_local_residual_generation",
        "failure_conditions": [
            "object-motion controls are indistinguishable from base candidate",
            "protected reread/proof/return effects degrade",
            "strongest-rival local advantage remains unchanged",
            "another merely partial adjacent gain appears",
        ],
    },
    materiality_policy=OBJECT_MOTION_MATERIALITY_POLICY,
)

TACTILE_INEVITABILITY_ADAPTER = ResidualTargetAdapter(
    target_id=TACTILE_INEVITABILITY_TARGET_ID,
    target_spec_version=TACTILE_TARGET_SPEC_VERSION,
    work_order_contract_version=TACTILE_WORK_ORDER_CONTRACT_VERSION,
    generation_contract_version=TACTILE_GENERATION_CONTRACT_VERSION,
    canonical_work_order_action=TACTILE_INEVITABILITY_SPEC.canonical_next_action,
    review_action=TACTILE_INEVITABILITY_SPEC.review_action,
    work_order_adapter=TACTILE_INEVITABILITY_SPEC.work_order_adapter,
    generation_schema=RESIDUAL_INTERVENTION_GENERATION_SCHEMA,
    worker_role=WorkerRole.RESIDUAL_INTERVENTION_GENERATOR,
    prompt_contract_id="autonomous.residual_intervention_generation.v1.tactile_inevitability",
    prompt_instructions=(
        "replace only the selected region",
        "produce one integrated replacement addressing all authoritative tactile units",
        "preserve current object-motion gains while adding physical force/contact necessity",
        "make material consequence feel physically unavoidable before explanation",
        "preserve current-best macro and reread gains",
        "avoid decorative vividness, new object lists, rival mimicry, abstract thesis language, and full rewrite",
    ),
    mechanism_contract=TACTILE_INEVITABILITY_SPEC.operational_definition,
    ablation_controls=TACTILE_INEVITABILITY_SPEC.target_specific_ablation_controls,
    reader_state_evaluation_focus=TACTILE_INEVITABILITY_SPEC.target_specific_reader_state_focus,
    stop_test_policy={
        "cycle_kind": "residual_stop_test",
        "pause_action": "pause_local_residual_generation",
        "failure_conditions": [
            "only generic vividness improves",
            "tactile and object-motion controls are indistinguishable",
            "protected reread/proof/return effects degrade",
            "strongest-rival local advantage remains unchanged",
            "another merely partial adjacent gain appears",
        ],
    },
    materiality_policy=TACTILE_MATERIALITY_POLICY,
)

HOSTILE_SCAFFOLD_VISIBILITY_ADAPTER = ResidualTargetAdapter(
    target_id=HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    target_spec_version=HOSTILE_SCAFFOLD_TARGET_SPEC_VERSION,
    work_order_contract_version=HOSTILE_SCAFFOLD_WORK_ORDER_CONTRACT_VERSION,
    generation_contract_version=HOSTILE_SCAFFOLD_GENERATION_CONTRACT_VERSION,
    canonical_work_order_action=HOSTILE_SCAFFOLD_VISIBILITY_SPEC.canonical_next_action,
    review_action=HOSTILE_SCAFFOLD_VISIBILITY_SPEC.review_action,
    work_order_adapter=HOSTILE_SCAFFOLD_VISIBILITY_SPEC.work_order_adapter,
    generation_schema=RESIDUAL_INTERVENTION_GENERATION_SCHEMA,
    worker_role=WorkerRole.RESIDUAL_INTERVENTION_GENERATOR,
    prompt_contract_id=(
        "autonomous.residual_intervention_generation.v1.hostile_scaffold_visibility"
    ),
    prompt_instructions=(
        "replace only the selected region; do not perform a broad rewrite",
        "reduce visible thesis/scaffold/explanatory pressure",
        "make the object field carry more of the meaning",
        "lexical tightening, one-word substitutions, and preserving target sentence architecture are insufficient",
        "materially address all five target units inside the selected region",
        "every hostile-scaffold target unit must be materially re-authored enough to clear the active materiality policy",
        "reduce scaffold by making the object sequence carry meaning, not by summarizing the thesis",
        "do not replace one visible thesis with another",
        "avoid colon-led thesis sentences and explanatory object-list lead-ins",
        "each target unit must solve a distinct local scaffold problem; do not reuse one object-list sentence across multiple units",
        "physical/object pressure may remain only when embodied in object relations, not as an abstract pressure label",
        "preserve embodied causal object field, tactile/object pressure, proof/no-answer carry, and opening-return gains",
        "do not delete proof/no-answer pressure",
        "do not flatten into summary",
        "do not imitate the rival",
        "preserve packet_0063 tactile/object gains and protected references outside the selected region",
        "surrounding protected context may remain stable",
        "do not make the prose vague, decorative, rival-like, summary-like, final, or phase-shift claiming",
    ),
    mechanism_contract=HOSTILE_SCAFFOLD_VISIBILITY_SPEC.operational_definition,
    ablation_controls=HOSTILE_SCAFFOLD_VISIBILITY_SPEC.target_specific_ablation_controls,
    reader_state_evaluation_focus=(
        HOSTILE_SCAFFOLD_VISIBILITY_SPEC.target_specific_reader_state_focus
    ),
    stop_test_policy={
        "cycle_kind": "residual_stop_test",
        "pause_action": "pause_until_generation_authorization",
        "failure_conditions": [
            "scaffold reduction deletes proof/no-answer pressure",
            "artifact becomes vague summary",
            "object field or tactile/object pressure weakens",
            "strongest-rival pressure is treated as defeated",
            "finality or phase-shift is claimed",
        ],
    },
    materiality_policy=HOSTILE_SCAFFOLD_MATERIALITY_POLICY,
)

RESIDUAL_TARGET_ADAPTERS = {
    OBJECT_MOTION_ADAPTER.target_id: OBJECT_MOTION_ADAPTER,
    TACTILE_INEVITABILITY_ADAPTER.target_id: TACTILE_INEVITABILITY_ADAPTER,
    HOSTILE_SCAFFOLD_VISIBILITY_ADAPTER.target_id: HOSTILE_SCAFFOLD_VISIBILITY_ADAPTER,
}

TACTILE_FORCE_TERMS = (
    "contact",
    "touch",
    "touched",
    "weight",
    "pressure",
    "press",
    "pressed",
    "resistance",
    "friction",
    "residue",
    "mark",
    "marked",
    "trace",
    "grain",
    "surface",
    "crack",
    "cracked",
    "break",
    "broken",
    "impact",
    "fall",
    "fell",
    "drop",
    "dropped",
    "release",
    "released",
    "settle",
    "settles",
    "settled",
    "dust",
    "shift",
    "shifted",
    "displace",
    "displaced",
    "drag",
    "dragged",
    "pull",
    "pulled",
    "push",
    "pushed",
    "slide",
    "slides",
)

TACTILE_DECORATIVE_TERMS = (
    "glimmering",
    "luminous",
    "beautiful",
    "velvet",
    "shimmering",
    "atmospheric",
    "vivid",
    "vividness",
)

TACTILE_ABSTRACT_TERMS = (
    "inevitability",
    "inevitable",
    "non-optional",
    "metaphysical proof",
)

HOSTILE_SCAFFOLD_EXPLANATION_TERMS = (
    "thesis",
    "scaffold",
    "explanation",
    "explains",
    "explained",
    "symbolic",
    "metaphysical",
    "signifies",
    "meaning",
    "means",
    "lesson",
    "message",
    "rule",
    "names it",
    "named",
)

HOSTILE_SCAFFOLD_LEAKAGE_TERMS = (
    "scaffold",
    "thesis",
    "final artifact",
    "finalization",
    "phase shift",
    "phase-shift",
    "human validation",
    "source manifest",
    "model_call_id",
    "artifact-set",
)

HOSTILE_GENERIC_VIVIDNESS_TERMS = (
    "luminous",
    "beautiful",
    "velvet",
    "shimmering",
    "atmospheric",
    "vivid",
    "vividness",
    "glittering",
)

HOSTILE_SUMMARY_COMPRESSION_TERMS = (
    "in summary",
    "this means",
    "the point is",
    "the theme is",
    "the artifact shows",
    "the text demonstrates",
)

HOSTILE_OBJECT_FIELD_TERMS = (
    "table",
    "dust",
    "spoon",
    "saucer",
    "ring",
    "cup",
    "crumb",
    "grain",
    "surface",
)

HOSTILE_TACTILE_PRESSURE_TERMS = (
    "contact",
    "pressure",
    "mark",
    "marks",
    "trace",
    "grain",
    "surface",
    "dust",
    "ring",
    "crumb",
    "break",
    "broken",
    "crack",
    "fall",
    "weight",
)


def get_residual_target_spec(target_id: str) -> ResidualTargetSpec | None:
    return RESIDUAL_TARGET_SPECS.get(target_id)


def require_residual_target_spec(target_id: str) -> ResidualTargetSpec:
    spec = get_residual_target_spec(target_id)
    if spec is None:
        raise ValueError(f"unsupported residual target: {target_id}")
    return spec


def supported_residual_target_ids() -> tuple[str, ...]:
    return tuple(RESIDUAL_TARGET_SPECS)


def get_residual_target_adapter(target_id: str) -> ResidualTargetAdapter | None:
    return RESIDUAL_TARGET_ADAPTERS.get(target_id)


def require_residual_target_adapter(target_id: str) -> ResidualTargetAdapter:
    adapter = get_residual_target_adapter(target_id)
    if adapter is None:
        raise ValueError(f"unsupported selected residual target: {target_id}")
    return adapter


def supported_residual_target_adapter_ids() -> tuple[str, ...]:
    return tuple(RESIDUAL_TARGET_ADAPTERS)


def target_adapter_metadata(target_id: str) -> dict[str, object]:
    adapter = require_residual_target_adapter(target_id)
    return {
        "target_adapter_id": adapter.adapter_id,
        "target_adapter_version": adapter.target_spec_version,
        "target_spec_version": adapter.target_spec_version,
        "work_order_contract_version": adapter.work_order_contract_version,
        "generation_contract_version": adapter.generation_contract_version,
        "generation_schema_name": adapter.generation_schema.name,
        "generation_schema_version": adapter.generation_schema.version,
        "prompt_contract_id": adapter.prompt_contract_id,
        "canonical_work_order_action": adapter.canonical_work_order_action,
        "review_action": adapter.review_action,
        "ablation_controls": list(adapter.ablation_controls),
        "reader_state_evaluation_focus": list(adapter.reader_state_evaluation_focus),
        "stop_test_policy": dict(adapter.stop_test_policy),
        "materiality_policy_id": adapter.materiality_policy.policy_id,
        "materiality_policy_version": adapter.materiality_policy.policy_version,
    }


def materiality_policy_payload(target_id: str) -> dict[str, object]:
    return require_residual_target_adapter(target_id).materiality_policy.to_dict()


def target_generation_readiness_failures(target_id: str) -> list[str]:
    adapter = require_residual_target_adapter(target_id)
    failures: list[str] = []
    if _is_placeholder_generation_contract(
        adapter.generation_contract_version,
        adapter.materiality_policy.policy_id,
    ):
        failures.append(
            "target generation contract is placeholder-only: "
            f"generation_contract_version={adapter.generation_contract_version}; "
            f"materiality_policy_id={adapter.materiality_policy.policy_id}"
        )
    if adapter.materiality_policy.primary_materiality_scope not in {
        "whole_selected_region",
        "target_bearing_scope",
    }:
        failures.append(
            "target materiality policy lacks a generation-enforceable scope: "
            f"{adapter.materiality_policy.primary_materiality_scope}"
        )
    if not adapter.prompt_contract_id.strip():
        failures.append("target prompt contract is missing")
    if target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        required_fields = {
            "scaffold_leakage_failures",
            "proof_no_answer_deletion_failures",
            "object_field_preservation_failures",
            "vagueness_or_summary_failures",
            "rival_mimicry_failures",
            "finality_or_phase_shift_claim_failures",
        }
        missing = sorted(required_fields - set(adapter.materiality_policy.failure_report_fields))
        if missing:
            failures.append(
                "hostile scaffold semantic validation contract is incomplete: "
                + ", ".join(missing)
            )
    return failures


def payload_has_placeholder_generation_contract(payload: dict[str, Any]) -> bool:
    return _is_placeholder_generation_contract(
        str(payload.get("generation_contract_version") or ""),
        str(payload.get("materiality_policy_id") or ""),
    )


def _is_placeholder_generation_contract(
    generation_contract_version: str,
    materiality_policy_id: str,
) -> bool:
    return (
        generation_contract_version in PLACEHOLDER_GENERATION_CONTRACT_VERSIONS
        or materiality_policy_id in PLACEHOLDER_MATERIALITY_POLICY_IDS
        or generation_contract_version.startswith("placeholder")
        or "placeholder" in materiality_policy_id
    )


def compile_tactile_target_units(
    *,
    inherited_units: list[dict[str, Any]],
    selected_text: str,
    parent_region_id: str,
) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    for inherited in inherited_units:
        compiled = compile_tactile_target_unit(
            inherited=inherited,
            selected_text=selected_text,
            parent_region_id=parent_region_id,
            index=len(units) + 1,
        )
        if compiled is not None:
            units.append(compiled)
    if units:
        return units

    for sentence in _sentences(selected_text):
        labels = extract_object_labels(sentence)
        if not labels:
            continue
        compiled = compile_tactile_target_unit(
            inherited={
                "unit_id": None,
                "before_text": sentence,
                "objects": labels,
                "target_effect": "",
                "current_motion_action_state": "",
                "current_consequence": "",
            },
            selected_text=selected_text,
            parent_region_id=parent_region_id,
            index=len(units) + 1,
        )
        if compiled is not None:
            units.append(compiled)
        if len(units) >= 3:
            break
    return units


def compile_tactile_target_unit(
    *,
    inherited: dict[str, Any],
    selected_text: str,
    parent_region_id: str,
    index: int,
) -> dict[str, object] | None:
    labels = _object_labels_from_unit(inherited)
    before_text = _sentence_matching_any(selected_text, tuple(labels))
    if not before_text:
        before_text = str(inherited.get("before_text") or "")
    if not before_text:
        return None
    role = _source_unit_role(
        labels=labels,
        before_text=before_text,
        inherited=inherited,
    )
    if role is None:
        return None
    relation = _current_physical_relation_for_role(
        role=role,
        labels=labels,
        before_text=before_text,
        inherited=inherited,
    )
    if relation is None:
        return None
    source_unit_id = str(inherited.get("unit_id") or "") or None
    unit_id = f"tactile_unit_{index:03d}"
    return {
        "target_unit_id": unit_id,
        "unit_id": unit_id,
        "source_target_unit_id": source_unit_id,
        "source_unit_role": role,
        "before_text": before_text,
        "before_text_sha256": sha256_text(before_text),
        "parent_region_id": parent_region_id,
        "involved_object_labels": labels,
        "objects": labels,
        "current_physical_relation": relation,
        "tactile_inevitability_deficit": _tactile_deficit_for_role(role),
        "allowed_operations": [
            "make contact, pressure, resistance, residue, displacement, or breakage materially causal",
            "preserve current object-motion consequence while adding physical necessity",
            "keep interpretation after material consequence",
        ],
        "forbidden_operations": list(TACTILE_INEVITABILITY_SPEC.forbidden_changes[:-2]),
        "forbidden_operation": [
            "add decorative detail",
            "add new object list",
            "add rival-like scene",
            "explain abstract inevitability",
            "full rewrite",
        ],
        "intended_first_read_effect": (
            "reader feels the material change as physically unavoidable before explanation"
        ),
        "target_effect": "reader feels material consequence before interpretation explains it",
        "protected_effects": [
            "current-best partial reread transformation",
            "record-bearing object field",
            "proof/no-answer gains",
            "opening-return/final-return gains",
            "reduced overexplanation",
            "current macro structure",
        ],
        "required_material_change": (
            "increase physical force/contact necessity, not quantity of sensory description"
        ),
        "material_change_required": True,
        "distinct_from_object_motion_basis": (
            "object-motion asks moved-therefore-changed; tactile inevitability "
            "asks why the material relation could not have failed to leave the mark"
        ),
    }


def validate_tactile_unit_map(unit_map: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    units = unit_map.get("target_units")
    if not isinstance(units, list) or not units:
        return ["tactile unit map has no target_units"]
    for index, unit in enumerate(units, start=1):
        if not isinstance(unit, dict):
            failures.append(f"tactile unit {index} is not an object")
            continue
        labels = [str(value) for value in unit.get("objects", []) if isinstance(value, str)]
        before_text = str(unit.get("before_text") or "")
        relation = str(unit.get("current_physical_relation") or "")
        role = str(unit.get("source_unit_role") or "")
        if not labels:
            failures.append(f"{unit.get('unit_id') or index} has no object labels")
        if not before_text.strip():
            failures.append(f"{unit.get('unit_id') or index} has no before_text")
        if not relation.strip():
            failures.append(f"{unit.get('unit_id') or index} has no current_physical_relation")
            continue
        inferred_role = _source_unit_role(
            labels=labels,
            before_text=before_text,
            inherited=unit,
        )
        relation_lower = relation.lower()
        if _is_surface_residue_role(labels, before_text) and any(
            term in relation_lower for term in ("fall", "impact", "break", "crack", "release")
        ):
            failures.append(
                f"{unit.get('unit_id') or index} assigns fall/break/impact relation to surface residue unit"
            )
        if role and inferred_role and role != inferred_role:
            failures.append(
                f"{unit.get('unit_id') or index} source_unit_role {role} conflicts with inferred {inferred_role}"
            )
        if inferred_role is None:
            failures.append(
                f"{unit.get('unit_id') or index} lacks enough source evidence for a distinct tactile relation"
            )
        elif not _relation_supported_by_role(inferred_role, relation_lower):
            failures.append(
                f"{unit.get('unit_id') or index} current_physical_relation is unsupported by source role {inferred_role}"
            )
    return failures


def validate_single_region_target_unit_alignment(
    unit_map: dict[str, Any],
    selected_region: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    selected_region_id = str(selected_region.get("selected_region_id") or "")
    selected_region_text = str(selected_region.get("selected_region_before_text") or "")
    normalized_region_text = _normalize_for_containment(selected_region_text)
    if not selected_region_id:
        failures.append("single-region target alignment missing selected_region_id")
    if not normalized_region_text:
        failures.append("single-region target alignment missing selected region text")
    target_units = unit_map.get("target_units")
    if not isinstance(target_units, list) or not target_units:
        return failures + ["single-region target alignment has no target_units"]
    for index, unit in enumerate(target_units, start=1):
        if not isinstance(unit, dict):
            failures.append(f"target unit {index} is not an object")
            continue
        material_change_required = unit.get("material_change_required") is True
        if not material_change_required:
            continue
        unit_id = str(unit.get("unit_id") or unit.get("target_unit_id") or index)
        before_text = str(unit.get("before_text") or "")
        normalized_before_text = _normalize_for_containment(before_text)
        if not normalized_before_text:
            failures.append(f"{unit_id} material target unit has no before_text")
            continue
        if normalized_before_text not in normalized_region_text:
            failures.append(
                "out_of_region_target_units_in_single_region_work_order: "
                f"{unit_id} before_text is outside selected region {selected_region_id}"
            )
        if unit.get("before_text_sha256") and unit.get("before_text_sha256") != sha256_text(before_text):
            failures.append(f"{unit_id} before_text_sha256 does not match before_text")
        source_region_id = _unit_source_region_id(unit)
        if source_region_id != selected_region_id:
            failures.append(
                "out_of_region_target_units_in_single_region_work_order: "
                f"{unit_id} source region {source_region_id or '<missing>'} "
                f"does not match selected region {selected_region_id}"
            )
        source_span = unit.get("source_span")
        if not isinstance(source_span, dict):
            failures.append(f"{unit_id} material target unit missing source_span metadata")
        elif str(source_span.get("region_id") or "") != selected_region_id:
            failures.append(
                "out_of_region_target_units_in_single_region_work_order: "
                f"{unit_id} source_span region "
                f"{source_span.get('region_id') or '<missing>'} does not match "
                f"selected region {selected_region_id}"
            )
    protected_references = unit_map.get("protected_reference_units", [])
    if protected_references is None:
        protected_references = []
    if not isinstance(protected_references, list):
        failures.append("protected_reference_units must be a list")
    else:
        for index, reference in enumerate(protected_references, start=1):
            if not isinstance(reference, dict):
                failures.append(f"protected reference unit {index} is not an object")
                continue
            if reference.get("material_change_required") is True:
                reference_id = str(
                    reference.get("unit_id")
                    or reference.get("reference_unit_id")
                    or index
                )
                failures.append(
                    f"{reference_id} protected_reference_units must not require material change"
                )
    return failures


def hostile_scaffold_mapping_failures(
    payload: dict[str, object],
    target_unit_ids: set[str],
) -> list[str]:
    failures: list[str] = []
    mappings = payload.get("target_unit_mappings")
    if not isinstance(mappings, list) or not mappings:
        return ["target_unit_mappings must not be empty"]
    seen: set[str] = set()
    preserved_notes = _joined_model_notes(payload)
    for index, item in enumerate(mappings):
        if not isinstance(item, dict):
            failures.append(f"target_unit_mappings[{index}] must be an object")
            continue
        unit_id = str(item.get("target_unit_id") or "")
        if unit_id not in target_unit_ids:
            failures.append(f"invented or unsupported target unit: {unit_id}")
        if unit_id in seen:
            failures.append(f"duplicate target unit mapping: {unit_id}")
        seen.add(unit_id)
        for field in (
            "before_text_sha256",
            "mechanism_operation",
            "material_relation_or_action",
            "visible_consequence",
            "intended_first_read_effect",
        ):
            if not str(item.get(field) or "").strip():
                failures.append(f"{unit_id}.{field} must not be empty")
        covered = {
            str(value)
            for value in item.get("covered_target_ids", [])
            if isinstance(value, str)
        }
        if unit_id and unit_id not in covered:
            failures.append(f"{unit_id}.covered_target_ids must include the unit id")
        protected = " ".join(
            str(value)
            for value in item.get("protected_effects_preserved", [])
            if isinstance(value, str)
        ).lower()
        preserved_notes += " " + protected
    missing = sorted(target_unit_ids - seen)
    if missing:
        failures.append(f"missing target unit IDs: {missing}")
    if not _contains_any(preserved_notes, ("proof", "answer", "no-answer")):
        failures.append("proof/no-answer carry is not recorded as preserved")
    if not _contains_any(preserved_notes, ("opening", "return", "reread", "final")):
        failures.append("opening-return/reread gains are not recorded as preserved")
    if not _contains_any(preserved_notes, ("object", "table", "dust", "spoon", "saucer", "ring")):
        failures.append("object/tactile causal field is not recorded as preserved")
    return failures


def replacement_hostile_scaffold_failures(
    *,
    replacement_text: str,
    selected_region_before_text: str,
    target_units: list[dict[str, object]],
    model_payload: dict[str, object],
) -> dict[str, list[str]]:
    replacement = replacement_text.strip()
    lower = replacement.lower()
    before_lower = selected_region_before_text.lower()
    failures: dict[str, list[str]] = {
        "scaffold_leakage_failures": [],
        "proof_no_answer_deletion_failures": [],
        "object_field_preservation_failures": [],
        "tactile_object_pressure_preservation_failures": [],
        "vagueness_or_summary_failures": [],
        "decorative_vividness_failures": [],
        "rival_mimicry_failures": [],
        "finality_or_phase_shift_claim_failures": [],
    }
    explanation_before = _term_count(before_lower, HOSTILE_SCAFFOLD_EXPLANATION_TERMS)
    explanation_after = _term_count(lower, HOSTILE_SCAFFOLD_EXPLANATION_TERMS)
    if explanation_before > 0 and explanation_after >= explanation_before:
        failures["scaffold_leakage_failures"].append(
            "visible thesis/scaffold/explanatory pressure was not reduced"
        )
    if _contains_any(lower, HOSTILE_SCAFFOLD_LEAKAGE_TERMS):
        failures["scaffold_leakage_failures"].append(
            "replacement contains explicit scaffold or artifact metadata leakage"
        )
    if _contains_any(lower, ("final artifact", "finalization", "phase shift", "phase-shift")):
        failures["finality_or_phase_shift_claim_failures"].append(
            "replacement contains finality or phase-shift language"
        )
    if "rival" in lower:
        failures["rival_mimicry_failures"].append(
            "replacement mentions or risks imitating the rival"
        )
    if _contains_any(lower, HOSTILE_GENERIC_VIVIDNESS_TERMS):
        failures["decorative_vividness_failures"].append(
            "replacement uses generic decorative vividness"
        )
    if _contains_any(lower, HOSTILE_SUMMARY_COMPRESSION_TERMS):
        failures["vagueness_or_summary_failures"].append(
            "replacement compresses into abstract summary"
        )
    if _word_count_for_validation(replacement) < max(
        45,
        int(_word_count_for_validation(selected_region_before_text) * 0.35),
    ):
        failures["vagueness_or_summary_failures"].append(
            "replacement is too short to carry the selected-region pressure"
        )
    object_terms_present = _terms_present(lower, HOSTILE_OBJECT_FIELD_TERMS)
    if len(object_terms_present) < 5:
        failures["object_field_preservation_failures"].append(
            "table/dust/spoon/saucer/ring causal field is not sufficiently present"
        )
    pressure_terms_present = _terms_present(lower, HOSTILE_TACTILE_PRESSURE_TERMS)
    if len(pressure_terms_present) < 4:
        failures["tactile_object_pressure_preservation_failures"].append(
            "tactile/object pressure is not sufficiently preserved"
        )
    unit_engagement_failures = _hostile_unit_engagement_failures(
        replacement_lower=lower,
        target_units=target_units,
    )
    failures["object_field_preservation_failures"].extend(unit_engagement_failures)
    notes = _joined_model_notes(model_payload)
    if not _contains_any(notes, ("proof", "answer", "no-answer")):
        failures["proof_no_answer_deletion_failures"].append(
            "model notes do not preserve proof/no-answer pressure"
        )
    if not _contains_any(notes, ("opening", "return", "reread", "final")):
        failures["proof_no_answer_deletion_failures"].append(
            "model notes do not preserve opening-return/reread gains"
        )
    return {key: value for key, value in failures.items() if value}


def _hostile_unit_engagement_failures(
    *,
    replacement_lower: str,
    target_units: list[dict[str, object]],
) -> list[str]:
    failures: list[str] = []
    for unit in target_units:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("unit_id") or unit.get("target_unit_id") or "")
        terms = {
            term
            for term in extract_object_labels(str(unit.get("before_text") or ""))
            if len(term) >= 3
        }
        terms.update(
            term
            for value in unit.get("objects", [])
            if isinstance(value, str)
            for term in extract_object_labels(value)
        )
        if not terms:
            continue
        if not _terms_present(replacement_lower, tuple(sorted(terms))):
            failures.append(f"{unit_id} is not materially engaged in replacement")
    return failures


def _joined_model_notes(payload: dict[str, object]) -> str:
    values: list[str] = []
    for key in (
        "protected_effects_notes",
        "forbidden_change_self_check",
        "intervention_plan",
    ):
        raw = payload.get(key)
        if isinstance(raw, list):
            values.extend(str(value) for value in raw if isinstance(value, str))
    return " ".join(values).lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _term_count(text: str, terms: tuple[str, ...]) -> int:
    return sum(text.count(term) for term in terms)


def _terms_present(text: str, terms: tuple[str, ...]) -> list[str]:
    return sorted({term for term in terms if term in text})


def _word_count_for_validation(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _unit_source_region_id(unit: dict[str, Any]) -> str:
    source_span = unit.get("source_span")
    if isinstance(source_span, dict) and source_span.get("region_id"):
        return str(source_span["region_id"])
    for key in ("source_region_id", "parent_region_id"):
        value = unit.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _normalize_for_containment(value: str) -> str:
    return " ".join(value.split())


def semantic_preflight_failures_for_work_order(payloads: dict[str, dict[str, Any]]) -> list[str]:
    packet = payloads.get("residual_work_order_packet", {})
    target_id = str(packet.get("selected_residual_target_id") or "")
    adapter = get_residual_target_adapter(target_id)
    if adapter is None:
        return [f"unsupported residual target: {target_id}"]
    failures: list[str] = []
    target_adapter_version = str(
        packet.get("target_adapter_version")
        or packet.get("target_spec_version")
        or ""
    )
    work_order_contract_version = str(packet.get("work_order_contract_version") or "")
    if target_adapter_version and target_adapter_version != adapter.target_spec_version:
        failures.append(
            "work order target adapter version "
            f"{target_adapter_version} is stale; current is {adapter.target_spec_version}"
        )
    if work_order_contract_version and work_order_contract_version != adapter.work_order_contract_version:
        failures.append(
            "work order contract version "
            f"{work_order_contract_version} is stale; current is {adapter.work_order_contract_version}"
        )
    if not target_adapter_version:
        failures.append("work order missing target_adapter_version")
    if not work_order_contract_version:
        failures.append("work order missing work_order_contract_version")
    unit_map = payloads.get("object_motion_target_unit_map", {})
    if target_id == TACTILE_INEVITABILITY_TARGET_ID:
        failures.extend(validate_tactile_unit_map(unit_map))
    if target_id == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
        failures.extend(
            validate_single_region_target_unit_alignment(
                unit_map,
                payloads.get("selected_intervention_region", {}),
            )
        )
    return failures


def tactile_mapping_failures(payload: dict[str, object], target_unit_ids: set[str]) -> list[str]:
    failures: list[str] = []
    mappings = payload.get("target_unit_mappings")
    if not isinstance(mappings, list) or not mappings:
        return ["target_unit_mappings must not be empty"]
    seen: set[str] = set()
    for index, item in enumerate(mappings):
        if not isinstance(item, dict):
            failures.append(f"target_unit_mappings[{index}] must be an object")
            continue
        unit_id = str(item.get("target_unit_id") or "")
        if unit_id not in target_unit_ids:
            failures.append(f"invented or unsupported target unit: {unit_id}")
        if unit_id in seen:
            failures.append(f"duplicate target unit mapping: {unit_id}")
        seen.add(unit_id)
        for field in (
            "before_text_sha256",
            "mechanism_operation",
            "material_relation_or_action",
            "visible_consequence",
            "intended_first_read_effect",
        ):
            if not str(item.get(field) or "").strip():
                failures.append(f"{unit_id}.{field} must not be empty")
        relation = " ".join(
            str(item.get(field) or "")
            for field in (
                "mechanism_operation",
                "material_relation_or_action",
                "visible_consequence",
                "intended_first_read_effect",
            )
        ).lower()
        if not any(term in relation for term in TACTILE_FORCE_TERMS):
            failures.append(f"{unit_id} does not encode contact/force/material necessity")
        if any(term in relation for term in TACTILE_ABSTRACT_TERMS):
            failures.append(f"{unit_id} explains tactile inevitability abstractly")
    missing = sorted(target_unit_ids - seen)
    if missing:
        failures.append(f"missing target unit IDs: {missing}")
    return failures


def replacement_tactile_failures(
    *,
    replacement_text: str,
    unit_labels: list[str],
) -> list[str]:
    lower = replacement_text.lower()
    failures: list[str] = []
    strong_force_terms = (
        "contact",
        "touch",
        "touched",
        "weight",
        "pressure",
        "press",
        "pressed",
        "resistance",
        "friction",
        "residue",
        "crack",
        "cracked",
        "break",
        "broken",
        "impact",
        "fall",
        "fell",
        "drop",
        "dropped",
        "release",
        "released",
        "settle",
        "settles",
        "settled",
        "displace",
        "displaced",
        "drag",
        "dragged",
        "pull",
        "pulled",
        "push",
        "pushed",
        "slide",
        "slides",
    )
    if not any(term in lower for term in strong_force_terms):
        failures.append("replacement does not encode contact/force/material necessity")
    if any(term in lower for term in TACTILE_DECORATIVE_TERMS):
        failures.append("replacement risks decorative/generic vividness")
    if any(term in lower for term in TACTILE_ABSTRACT_TERMS):
        failures.append("replacement explains inevitability abstractly")
    if "rival" in lower:
        failures.append("replacement risks rival mimicry")
    present_labels = [label for label in unit_labels if label.lower() in lower]
    if len(set(present_labels)) < min(3, len(set(unit_labels))):
        failures.append("replacement does not preserve enough target object labels")
    return failures


def _object_labels_from_unit(unit: dict[str, Any]) -> list[str]:
    labels = unit.get("objects") or unit.get("involved_object_labels") or []
    if not isinstance(labels, list):
        return []
    result = []
    for label in labels:
        text = str(label).strip()
        if text and text not in result:
            result.append(text)
    return result


def extract_object_labels(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "that",
        "this",
        "with",
        "into",
        "where",
        "what",
        "when",
        "while",
        "before",
        "after",
        "only",
        "each",
        "same",
        "there",
        "room",
        "world",
        "thing",
        "things",
        "change",
        "surface",
    }
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower())
    labels = []
    for word in words:
        if len(word) < 3 or word in stop:
            continue
        if word not in labels:
            labels.append(word)
        if len(labels) >= 5:
            break
    return labels


def _source_unit_role(
    *,
    labels: list[str],
    before_text: str,
    inherited: dict[str, Any],
) -> str | None:
    haystack = " ".join(
        [
            before_text,
            " ".join(labels),
            str(inherited.get("source_unit_role") or ""),
            str(inherited.get("current_motion_action_state") or ""),
            str(inherited.get("current_consequence") or ""),
            str(inherited.get("target_effect") or ""),
        ]
    ).lower()
    label_text = " ".join(labels).lower()
    if any(term in label_text for term in ("spoon", "saucer", "fall", "crack", "break")):
        return "impact_breakage"
    if any(term in label_text for term in ("ring", "grain", "crumb", "cup")):
        return "contact_residue_displacement"
    if _is_surface_residue_role(labels, before_text):
        return "surface_residue_disturbance"
    if any(term in haystack for term in ("crack", "break", "broken", "fall", "impact", "saucer")):
        return "impact_breakage"
    if any(term in haystack for term in ("ring", "grain", "crumb", "residue", "wet", "drag")):
        return "contact_residue_displacement"
    if any(term in haystack for term in TACTILE_FORCE_TERMS):
        return "material_contact_pressure"
    if str(inherited.get("current_motion_action_state") or "").strip() and str(
        inherited.get("current_consequence") or ""
    ).strip():
        return "material_contact_pressure"
    return None


def _is_surface_residue_role(labels: list[str], before_text: str) -> bool:
    label_text = " ".join(labels).lower()
    if any(term in label_text for term in ("spoon", "saucer", "fall", "crack", "break")):
        return False
    if any(term in label_text for term in ("dust", "surface", "residue")):
        return True
    haystack = before_text.lower()
    return any(term in haystack for term in ("dust", "surface", "residue", "settle", "settles"))


def _current_physical_relation_for_role(
    *,
    role: str,
    labels: list[str],
    before_text: str,
    inherited: dict[str, Any],
) -> str | None:
    if role == "surface_residue_disturbance":
        return "contact, passage, and settling leave residue on the surface"
    if role == "impact_breakage":
        return "release, weight, impact, or breakage leaves a visible material change"
    if role == "contact_residue_displacement":
        return "contact, pressure, residue, and displacement alter the surface trace"
    if role == "material_contact_pressure":
        action = str(inherited.get("current_motion_action_state") or "").strip()
        consequence = str(inherited.get("current_consequence") or "").strip()
        if action and consequence:
            return f"{action}; {consequence}"
        if any(term in before_text.lower() for term in TACTILE_FORCE_TERMS) and labels:
            return "material contact leaves a visible consequence"
    return None


def _tactile_deficit_for_role(role: str) -> str:
    if role == "surface_residue_disturbance":
        return "surface residue should feel caused by contact and passage, not static atmosphere"
    if role == "impact_breakage":
        return "impact or breakage should feel physically necessary, not merely narrated"
    if role == "contact_residue_displacement":
        return "contact and residue can become more materially necessary without decorative atmosphere"
    return "material relation can become more physically necessary without generic vividness"


def _relation_supported_by_role(role: str, relation_lower: str) -> bool:
    if role == "surface_residue_disturbance":
        return any(term in relation_lower for term in ("contact", "passage", "settling", "residue", "surface", "dust"))
    if role == "impact_breakage":
        return any(term in relation_lower for term in ("impact", "break", "crack", "weight", "release", "fall"))
    if role == "contact_residue_displacement":
        return any(term in relation_lower for term in ("contact", "pressure", "residue", "displacement", "grain", "trace"))
    if role == "material_contact_pressure":
        return any(term in relation_lower for term in TACTILE_FORCE_TERMS) or bool(relation_lower.strip())
    return False


def _sentence_matching_any(text: str, terms: tuple[str, ...]) -> str:
    lowered_terms = tuple(term.lower() for term in terms if term)
    for sentence in _sentences(text):
        lower = sentence.lower()
        if any(term in lower for term in lowered_terms):
            return sentence
    return ""


def _sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?;])\s+", normalized) if sentence.strip()]
