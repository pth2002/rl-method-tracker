# Triage rules for the candidate pool (v2)

Read only the title and abstract. Assign exactly one label.

| label | meaning |
|---|---|
| `rl_method` | Proposes a new or modified training-time RL algorithm component: loss or objective, advantage or baseline estimation, clipping or trust region, importance weighting or off-policy correction, rollout sampling or filtering that feeds the gradient, task-agnostic reward shaping (e.g. length penalties), KL or entropy regularisation, credit assignment, or an optimiser designed specifically for RL training of language models. Components for multimodal or agent RL count. |
| `rl_application` | Uses existing RL algorithms, possibly with task-specific rewards, data or environments, to train a model for a task or domain. Domain-specific reward models or verifiers also go here. |
| `analysis` | Empirical study, reproduction or ablation that proposes no new method. |
| `systems` | Training systems, asynchronous pipelines, rollout engines, memory or throughput work; the objective is unchanged. |
| `preference_offline` | Offline preference optimisation in the DPO family. |
| `distillation` | The main objective matches a teacher, including on-policy distillation. |
| `other` | Surveys, benchmarks, inference-time methods, SFT objectives, generic reward-model fitting, or not about RL training of language models. |

## Two extra fields for every paper

- `scope` (only for `rl_method`, otherwise null):
  - `general`: the component is the paper's main contribution and is presented as a general RL-for-LLM technique, typically evaluated on general reasoning, math, code or several domains.
  - `embedded`: the component is introduced inside a paper whose main contribution is a task, domain, agent or application, even if the component could transfer.
- `is_model_report`: true when the paper is a model release or technical report (e.g. "X Technical Report", a named model family), for any label.

## Boundary rules

- Label from what the abstract says, not from what you know about the paper. A model report whose abstract names a new RL component is `rl_method`. A model report whose abstract describes no RL component gets the label its abstract supports and `is_model_report: true`; such reports receive a full-text pass later.
- A component that only works with a domain-specific reward is `rl_application`. A domain-agnostic component that the paper evaluates on one domain is `rl_method`; decide `scope` by what the paper's main contribution is.
- A paper that proposes a method and also does extensive analysis is `rl_method`.
- A paper that names a new method but whose abstract does not say what changes in the RL algorithm: `rl_method` with `confidence: low`.
- An offline objective that regresses on absolute rewards rather than preference pairs is `rl_method` with component `offpolicy`.
- In a distillation paper, a transferable RL component does not change the label unless the RL update, not teacher matching, is the main objective.
- Use `confidence: low` whenever the abstract leaves the label genuinely open. Do not default to medium.

## Output

One JSON object per paper, one per line. The ids and names below are placeholders.

```json
{"arxiv": "2501.00000", "label": "rl_method", "scope": "general", "is_model_report": false,
 "in_tech_report": false, "method_name": "XPO", "component": "clipping",
 "symptoms": ["entropy_collapse"], "confidence": "high",
 "evidence": "we propose XPO, which decouples the lower and upper clip ranges"}
```

- `in_tech_report`: kept for compatibility; set it equal to `is_model_report` when the label is `rl_method`, else false.
- `method_name`: acronym or short name, or null.
- `component`: one of advantage, clipping, aggregation, sampling, length, offpolicy, moe, entropy, kl, multi_reward, credit_assignment, other, or null when the label is not `rl_method`.
- `symptoms`: ids from `data/symptoms.yaml` the method targets; may be empty.
- `confidence`: high, medium or low.
- `evidence`: at most 20 words copied from the abstract.
