# AngelCopilot Deal Assessment Rubric

## Seven factors

Assess all seven factors. The default weights remain stable so companies can be compared. Product measures customer value and performance today; Defensibility measures the durability of the advantage.

| Factor | Weight | Score 1 anchor | Score 3 anchor | Score 5 anchor |
|---|---:|---|---|---|
| Team | 25% | Material execution or integrity weaknesses | Relevant team with gaps and some execution evidence | Exceptional founder-market fit and independently supported execution; key roles covered |
| Market | 20% | Weak urgency, inaccessible demand or adverse timing | Clear customer need and reachable wedge, with competitive constraints | Strong urgent demand, accessible buyers and compelling timing, supported by specific evidence |
| Product | 15% | Poor customer value or material technical weakness | Working product addresses a clear problem; performance remains partly unproven | Independently demonstrated advantage and reliable delivery for the company's stage |
| Traction | 15% | Weak or deteriorating customer validation | Credible paid adoption or stage-appropriate pilot evidence | Exceptional repeatable demand, retention and conversion for the company's stage |
| Unit Economics | 10% | Structurally unattractive delivery economics | Plausible economics with cost and scalability questions | Fully supported margins, acquisition/delivery costs and capital needs consistent with scaling |
| Defensibility | 10% | Advantage is readily copied or structurally weak | Plausible moat mechanism that is not yet compounding | Evidence that switching costs, IP, data or distribution advantages are compounding |
| Terms | 5% | Price or rights materially undermine the investor's net payoff | Reasonable price and understandable security with trade-offs | Attractive price and security economics; transparent fees, conversion and investor protections |

Use 0–5 with at most one decimal. Scores 2 and 4 interpolate between anchors; 0 is reserved for demonstrated extreme weakness, never absence of information. Write the evidence that supports each judgment and what holds its score back. For genuinely unassessable factors, use null / Not Scored, explain the gap and do not manufacture an aggregate. Report weighted totals only when all positively weighted categories can be scored, with score coverage separately. Keep confidence (high / medium / low / unknown) distinct from company quality.

Anchor evidence to stage and business model: pre-seed customer experiments differ from seed retention; hardware needs reliability, yield, warranty and working-capital evidence; biotech needs scientific, regulatory and manufacturing milestones. Avoid demanding mature SaaS metrics from every startup. A preference mismatch belongs in investor suitability, not a fabricated low company score.

Apply supported `evaluation_weight_overrides`, merge with defaults and normalize to 100%. Show effective weights. These are preference weights, not predictive coefficients.

## Recommendation is an investment judgment

The 4.2 / 3.5 bands are retired as verdict rules. Scores are descriptive, not calibrated return predictors. Judge the opportunity at the actual terms and the investor's normal cheque, using evidence, net economics and known constraints.

- **INVEST — a normal cheque now:** the investment case is attractive, material evidence is sufficient, terms and net outcome potential can be underwritten, and the normal cheque fits the investor's stated constraints. Specify the total cash commitment and sizing reason. Do not defer material diligence until after an INVEST call.
- **WAIT — zero now:** a material but realistically resolvable evidence, terms or suitability gap blocks commitment. State the verifiable conditions that could change the call. A deadline or attractive story is not a reason to suggest an exploratory cheque.
- **PASS — zero under the current opportunity/terms:** a deal-breaking fact, incompatible constraint or unattractive risk/reward case defeats the opportunity. State what materially different terms or facts, if any, would justify reopening it. Do not demand unnecessary founder work on an opportunity already ruled out.

A fatal issue yields PASS; an unresolved blocker prevents INVEST. Distinguish those from ordinary residual venture risk, which can remain in an INVEST. Do not let a high score cancel a blocker. Do not make lack of publicly available private-company data evidence of fraud or poor performance.

Use cheque minimum, typical and maximum only from the investor profile. If no complete range is stored, do not recommend a cheque or model returns using an invented ticket; ask the investor to set the range. Recommend within the stored range; a below-minimum probe is not INVEST. Moving away from the typical ticket requires an explicit conviction, concentration or known budget reason. Quote all-in cash outlay, including disclosed entry expenses, and check the subscription minimum on the appropriate fee basis. Do not invent remaining portfolio capacity.

Follow-on participation is not part of the default case or sizing. Lack of pro-rata is not by itself a blocker for someone who rarely follows on. Reporting and information access can still matter to a passive investor. Only discuss later participation if the user asks or a particular security provision materially changes the current economics.

## Net return stress tests

Model one normal cheque with no follow-ons. Use four distinct outcomes: loss / zero recovery, bear / partial recovery, base and upside. Probabilities are subjective assumptions, sum to 100%, and the zero-recovery case must have positive probability. State the source or reasoning for valuation and outcome assumptions; do not invent probabilities that look statistically calibrated.

Disclose total cash outlay, deployable capital, fee rate and whether fees are deducted or added, post-money entry valuation, currency conversion, illustrative entry ownership, future dilution and exit ownership, carry rate and its capital-return basis, horizon, and excluded taxes/additional expenses. SAFE cap-based ownership is only an illustration, not a guaranteed conversion price. Exit values must represent equity value distributable to the modeled holding after the assumed debt and preference waterfall; disclose simplifications. Unknown conversion, senior claims or cost terms may make a credible model unavailable.

Calculate net proceeds, net MOIC and annualized return for each scenario from those inputs. With one outflow and one terminal receipt, annualized return = net MOIC^(1/years) − 1; actual intermediate cash flows require a cash-flow model. Show probability of total loss separately from probability of returning less than cash paid. Show assumption-weighted proceeds alongside their reliance on the upside case and a price sensitivity. Do not headline “expected IRR”; annualizing expected proceeds and averaging scenario annualized returns are different operations and neither is a forecast.

If a personal hurdle is supplied, identify its basis. The optional `base_case_return_hurdle` profile field compares the base case's net annualized return, not an expected IRR. If no hurdle exists, identify the decision as a qualitative investment judgment and do not claim a personal hurdle was met. Leave the model unavailable when inputs cannot credibly be specified; this blocks an INVEST rather than fabricating a favourable return case.
