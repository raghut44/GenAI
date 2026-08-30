# Interview Prep Guide: Harness Engineering & LLM Evaluation

This guide is built around your resume line:

> **Harness Engineering** — golden-dataset regression suites, automated LLM-output scoring, CI evaluation gates for agent-generated code; guardrails & output-safety evaluation

It has two parts:
1. **Tutorial section** — plain-English explanations of each concept, so you can speak about them confidently even if you're rusty on specifics.
2. **Q&A section** — likely interview questions with model answers you can adapt to your actual project details.

Wherever you see `[YOUR DETAIL]`, swap in specifics from your real work (numbers, tool names, team size) — interviewers can tell canned answers apart from real ones, and specifics are what make an answer memorable.

---

## PART 1: TUTORIAL — Understand It, Don't Just Memorize It

### 1.1 What is a "test harness" in this context?

A test harness is the surrounding infrastructure that runs a system under controlled conditions and checks its behavior — inputs go in, outputs get captured, and something judges whether the outputs are correct/safe/good enough. For LLM and agent systems, a harness typically:
- Feeds a fixed or generated set of prompts/tasks to the model or agent
- Captures the full output (text, code, tool calls, actions)
- Scores that output against some standard
- Reports pass/fail or a quality score, ideally automatically, ideally in CI

The reason harnesses matter more for LLMs than traditional software: LLM outputs are non-deterministic and open-ended, so you can't just do `assert output == expected`. You need scoring logic that tolerates variation while still catching real regressions.

### 1.2 Golden-dataset regression suites

**What it is:** A "golden dataset" is a curated, versioned set of input/expected-output pairs (or input + rubric) that represents known-good behavior. A "regression suite" runs the current model/pipeline against that dataset every time something changes (new prompt, new model version, new code) to catch cases where behavior gets *worse*, not just different.

**Why it exists:** Without it, teams ship a prompt tweak or model upgrade, and something that used to work silently breaks for a subset of cases. Golden sets convert "we think it's better" into "we can show it's not worse on these N known cases, and here's how much better on the rest."

**How they're usually built:**
- Sourced from real production failures/edge cases (the most valuable ones — bugs you've already hit)
- Sourced from synthetic generation (LLM-generated edge cases, adversarial prompts)
- Human-labeled or rubric-scored "ideal" answers
- Versioned (e.g., in git or a dataset registry) so you can track when the golden set itself changes and why

**Key tension to be able to discuss:** Golden sets go stale. If you never add new cases, you get false confidence; if you refresh them constantly, you lose the ability to compare apples-to-apples across model versions. Good answer here shows you understand *dataset maintenance* as a real engineering problem, not just "we had a CSV of test cases."

### 1.3 Automated LLM-output scoring

**What it is:** Since exact-match assertions don't work well for free-text or code output, scoring usually falls into a few families:

| Approach | How it works | Good for | Weakness |
|---|---|---|---|
| **Exact/structural match** | Regex, JSON schema validation, unit tests on generated code | Structured output, code correctness | Too rigid for prose |
| **Rule-based / heuristic** | Keyword checks, length bounds, format checks, banned-phrase lists | Cheap guardrail-style checks | Shallow, easy to game |
| **Embedding similarity** | Compare output embedding to reference embedding (cosine similarity) | Semantic closeness to a reference answer | Doesn't catch subtle correctness issues |
| **LLM-as-judge** | A separate (often stronger) model scores the output against a rubric | Nuanced quality, tone, helpfulness, safety | Judge model has its own biases/inconsistency; needs calibration |
| **Execution-based** | Run generated code, check it compiles/passes tests | Code-gen correctness | Only works when output is executable |

**Important nuance to mention in an interview:** LLM-as-judge scoring needs its own validation — you check judge-model scores against human labels on a sample to make sure the judge is actually correlated with human judgment ("judge calibration" or "meta-evaluation"). Saying this shows maturity beyond "we just asked GPT to grade it."

### 1.4 CI evaluation gates for agent-generated code

**What it is:** Wiring the above scoring into CI/CD so that agent- or LLM-generated code changes can't merge (or can't be promoted to production) unless they pass evaluation thresholds — similar in spirit to unit test gates, but scoring quality/safety/correctness of generated artifacts rather than hand-written code.

**Typical pipeline shape:**
1. Agent generates code/output for a PR or task
2. Harness runs the golden-dataset suite + relevant unit/integration tests
3. Scoring layer (rule-based + LLM-judge + execution-based) produces a score or pass/fail
4. CI gate blocks merge if score < threshold, or flags for human review if borderline
5. Results logged for trend tracking (is quality drifting up/down over time?)

**Design decisions worth being able to talk through:**
- **Hard gate vs. soft gate:** Do you block merges automatically, or surface a warning for human judgment? Usually starts soft, tightens over time once you trust the metric.
- **Threshold setting:** Thresholds are usually empirically tuned against historical data, not arbitrary — you want few false blocks and few missed regressions.
- **Flakiness control:** LLM outputs vary run-to-run; gates often average over multiple samples or use temperature=0 for determinism where possible.
- **Speed vs. rigor:** Full golden-set runs can be slow/expensive; often there's a fast subset run on every PR and a full nightly run.

### 1.5 Guardrails & output-safety evaluation

**What it is:** Guardrails are checks (often layered — pre-generation, during, and post-generation) that catch unsafe, harmful, or policy-violating outputs before they reach a user or downstream system. Output-safety evaluation is the harness that continuously measures how well those guardrails are working.

**Common guardrail types:**
- **Input-side:** prompt injection detection, jailbreak pattern detection
- **Output-side:** toxicity/harm classifiers, PII leakage detection, policy-violation classifiers, hallucination/factuality checks
- **Action-side (for agents):** permission checks before tool calls, sandboxing, rate limits on destructive actions

**Evaluation approach:**
- Curated "red team" datasets — known attack prompts / edge cases the guardrail should catch
- Precision/recall framing: guardrails that are too aggressive block legitimate use (false positives hurt usability); too loose and harmful content leaks through (false negatives are safety incidents)
- Ongoing adversarial testing — since bad actors adapt, the eval suite needs new attack patterns added over time, not just a static set

**Good interview framing:** Guardrail evaluation is fundamentally a precision/recall tradeoff problem, and part of the engineering work is deciding *where* on that curve the product should sit, then measuring whether you're actually there — not just "we added a safety filter."

---

## PART 2: INTERVIEW QUESTIONS + MODEL ANSWERS

### Behavioral / experience questions

**Q1: Walk me through how you built (or contributed to) the evaluation harness at [YOUR COMPANY].**

*Model answer structure (STAR):*
> "The problem was [YOUR DETAIL — e.g., 'we had no systematic way to know if a prompt or model change made agent-generated code better or worse before it shipped']. I worked on a harness that ran a golden-dataset regression suite — [X] curated cases sourced from [production failures / hand-written edge cases / synthetic generation] — against every candidate change. We scored outputs using a mix of [execution-based tests for code correctness] and [LLM-as-judge scoring for quality/tone], and wired the result into CI as a gate so a PR couldn't merge if it dropped below [threshold] on the suite. The result was [X% reduction in regressions shipped / faster iteration because engineers trusted the gate / caught Y specific incident before it hit production]."

**Q2: Tell me about a time a golden dataset or eval metric gave you a false signal. How did you catch it?**

*Model answer approach:* Pick a real or plausible failure mode — e.g., the LLM-judge was biased toward longer answers, or the golden set was stale and didn't reflect a new use case, or a threshold was too strict and blocked good code. Show: (1) how you noticed (metric disagreed with human intuition / a good PR got blocked), (2) how you diagnosed it (sampled cases, compared judge score to human label), (3) what you changed (recalibrated judge, added cases, adjusted threshold).

**Q3: How do you decide what goes into a golden dataset?**

> "I prioritize real production failures first — those are proof the case matters. Then I add synthetic edge cases to cover known risk areas [prompt injection, ambiguous instructions, edge-case code patterns]. I also keep the set versioned so we can tell whether a metric change is because the *model* got better/worse or because the *dataset* changed — those are easy to conflate if you're not careful."

---

### Technical / conceptual questions

**Q4: Why can't you just use exact-match assertions for LLM outputs the way you would for traditional unit tests?**

> "Because LLM outputs are non-deterministic and can be correct in multiple valid phrasings or implementations. Exact match would produce huge numbers of false failures. Instead we use a layered approach — execution-based checks for anything that has an objective pass/fail (does the generated code run and pass tests), and softer scoring like embedding similarity or LLM-as-judge for open-ended quality, so we tolerate valid variation while still catching real regressions."

**Q5: How do you validate that your LLM-as-judge scorer is actually reliable?**

> "You treat the judge itself as a model that needs evaluation. We'd sample a subset of judge scores, get human labels on the same cases, and check correlation — agreement rate, or something like Cohen's kappa if scores are categorical. If the judge disagreed with humans in a systematic way — say, it over-rewarded verbosity — we'd adjust the rubric or few-shot examples in the judge prompt and re-check."

**Q6: How would you design a CI gate for agent-generated code without slowing every PR down to a crawl?**

> "Tiered evaluation: a fast, cheap subset of the golden set (maybe the highest-signal or highest-risk cases) runs on every PR for quick feedback, and the full suite runs nightly or pre-release. You can also cache results when the underlying model/prompt hasn't changed. The goal is fast feedback for common cases and full rigor before anything actually ships."

**Q7: What's the difference between a guardrail and an evaluation metric?**

> "A guardrail acts at runtime — it's the thing that actually blocks or filters unsafe output before a user sees it. An evaluation metric measures how well the guardrails (and the system generally) are performing, usually offline against a curated dataset. You need both: guardrails without evaluation mean you don't know if they're actually working; evaluation without guardrails means you're only measuring the problem, not preventing it."

**Q8: How do you balance guardrail strictness against usability?**

> "It's a precision/recall tradeoff. Too strict and you get false positives — legitimate requests get blocked, which hurts usability and trust. Too loose and harmful content leaks through. I'd look at it empirically: run the guardrail against a labeled red-team + legitimate-use dataset, look at the precision/recall curve, and pick an operating point based on the actual cost of each error type for that product — a coding assistant might tolerate more false positives than a customer-facing chatbot, for example."

**Q9: How do you keep an eval suite from going stale?**

> "Treat it like living infrastructure, not a one-time artifact. New production failures get triaged and added as regression cases. Red-team/adversarial cases get refreshed periodically since attack patterns evolve. And periodically you audit whether old cases are still relevant — sometimes the product changes and a case that used to matter no longer reflects real usage."

**Q10: (System-design style) Design an evaluation pipeline for a coding agent that opens PRs automatically.**

*Structure your answer around these stages — this shows systems thinking:*
1. **Trigger:** Agent generates a PR (code diff + description)
2. **Static checks:** linting, type checks, existing unit tests
3. **Golden-set regression:** run agent against curated coding tasks with known-good solutions; score via execution (does it pass hidden tests) — fast subset on every PR
4. **LLM-judge review:** score code quality/style/readability against a rubric, since not everything is testable by execution
5. **Guardrail check:** scan for unsafe patterns (secrets, destructive commands, disallowed dependencies)
6. **Gate decision:** hard block below a floor threshold; human review queue for borderline scores; auto-approve above a high threshold
7. **Feedback loop:** log outcomes (was a merged PR later reverted? did a blocked PR turn out to be fine?) to recalibrate thresholds over time

---

### Curveball / probing follow-ups (be ready for these)

- *"What would you do if the eval metric said quality improved but users complained more?"* → Trust the user signal, treat it as a sign the metric doesn't capture something real (metric-target mismatch); go back and expand the golden set or judge rubric to include the missed dimension.
- *"How do you prevent people from gaming the eval gate?"* → Diversify scoring signals so no single cheap heuristic can be over-optimized; periodically rotate/add unseen golden cases; treat suspiciously perfect scores as a signal to investigate, not celebrate.
- *"What's the cost of running this in CI, and how do you manage it?"* → Talk about sampling strategy, caching, tiered fast/slow suites, and choosing cheaper judge models for the fast path with a stronger judge for full runs.

---

## PART 3: QUICK-REFERENCE GLOSSARY

- **Golden dataset:** curated, versioned set of known-good input/output pairs used as a regression baseline.
- **LLM-as-judge:** using a (typically strong) model to score another model's output against a rubric.
- **Judge calibration:** validating that an LLM-judge's scores correlate with human judgment.
- **CI evaluation gate:** an automated pass/fail check wired into CI that blocks merges/deploys below a quality threshold.
- **Guardrail:** a runtime check that blocks or filters unsafe/policy-violating input or output.
- **Precision/recall tradeoff (in safety context):** precision = how often a flagged item is truly bad; recall = how much of the truly bad content gets caught. Guardrail tuning is choosing where to sit on this curve.
- **Red-teaming:** proactively testing a system with adversarial inputs to find safety/robustness gaps.
- **Regression:** a case that used to work correctly and now doesn't, after a change.

---

## PART 4: CONFIDENCE TIPS FOR THE INTERVIEW

1. **Lead with the "why" before the "what."** Interviewers remember candidates who explain *why* a golden dataset matters (catching silent regressions) more than those who just define it.
2. **Have one detailed war story ready.** A specific bug caught by the harness, or a threshold that was wrong and got fixed, shows real hands-on experience far better than reciting definitions.
3. **Use the precision/recall framing whenever safety/guardrails come up** — it signals you think about tradeoffs, not just "we added a filter."
4. **If you don't remember an exact number** (e.g., dataset size, threshold value), say the shape of the answer honestly: *"I don't remember the exact figure, but directionally it was [small/large], and the reasoning behind it was..."* — this reads as far more credible than guessing a fake-sounding stat.
5. **Practice saying the tutorial section (Part 1) out loud once or twice.** The goal isn't memorization — it's being able to explain each concept in your own words without hesitation.

---

*Fill in the `[YOUR DETAIL]` placeholders with your real numbers, tools, and outcomes before your interview — that's what will make these answers land as authentic rather than generic.*
