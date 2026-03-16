# Alpha Hunt - Autonomous Discovery Skill

## Trigger
`/alpha-hunt` or `/alpha-hunt [focus]`

## Description
Runs a complete autonomous alpha discovery cycle that scouts for opportunities, generates hypotheses, tests them rigorously, and promotes winners to production.

## Focus Areas (Optional)
- `commodities` - Energy, metals, agriculture ETFs
- `semiconductors` - DRAM, supply chain, equipment
- `macro` - Rates, yields, regime shifts
- `sectors` - Sector rotation, relative value
- `alternative` - Blogs, sentiment, novel data
- (default) - Scan everything

## Workflow

### Phase 1: Reconnaissance (Parallel)
Launch 3 agents simultaneously:

1. **Market Scanner Agent**
   - Scan all universes for anomalies
   - Identify overbought/oversold conditions
   - Check current regime
   - Find momentum/mean-reversion candidates

2. **Data Scout Agent**
   - Check blog sources for new articles
   - Look for novel data opportunities
   - Verify existing data sources still work
   - Identify gaps in coverage

3. **Knowledge Query Agent**
   - Query recent experiment results
   - Find open research leads
   - Identify what worked/failed recently
   - Get causal relationships to test

### Phase 2: Hypothesis Generation (Sequential)
After Phase 1 completes:

1. **Hypothesis Generator Agent**
   - Synthesize reconnaissance results
   - Generate 5-10 ranked hypotheses
   - Each hypothesis includes:
     - Clear testable statement
     - Data requirements
     - Expected mechanism
     - Priority score

### Phase 3: Parallel Testing
Launch N research workers (up to 5):

For each top hypothesis:
1. Acquire necessary data
2. Generate features
3. Run backtest
4. MCPT validation (1000 permutations)
5. Walk-forward OOS validation
6. Bootstrap confidence intervals

### Phase 4: Validation & Promotion (Sequential)

1. **Critic Agent**
   - Review all significant results (p < 0.05)
   - Check for lookahead bias
   - Verify economic sense
   - Flag any concerns

2. **Promotion & Learning**
   - Add validated strategies to paper trading queue
   - Record all results in knowledge base
   - Update causal relationship graph
   - Generate next cycle priorities

## Output

Results saved to: `~/quant_results/alpha_hunt/`

```
alpha_hunt/
├── cycle_YYYYMMDD_HHMMSS/
│   ├── reconnaissance.json      # Phase 1 results
│   ├── hypotheses.json          # Phase 2 ranked ideas
│   ├── test_results/            # Phase 3 per-hypothesis
│   │   ├── hypothesis_1.json
│   │   ├── hypothesis_2.json
│   │   └── ...
│   ├── validation.json          # Phase 4 critic review
│   ├── promoted_strategies.yaml # Ready for paper trading
│   └── cycle_summary.md         # Human-readable summary
└── knowledge_updates.json       # What we learned
```

## Example Prompts

```
# Full autonomous cycle
/alpha-hunt

# Focused on commodities
/alpha-hunt commodities

# Focus on novel data sources
/alpha-hunt alternative

# After running, to see results:
Show me the results from the last alpha hunt cycle
```

## Implementation Notes

The skill should:
1. Use Task tool with `run_in_background=false` for sequential phases
2. Use parallel Task calls for reconnaissance and testing phases
3. Track all agent outputs and synthesize into final report
4. Update knowledge base with learnings
5. Be resumable if interrupted

## Success Metrics

A successful cycle produces:
- [ ] At least 5 hypotheses tested
- [ ] Statistical validation on all tests
- [ ] At least 1 significant finding (or documented null results)
- [ ] Knowledge base updated
- [ ] Next priorities identified
