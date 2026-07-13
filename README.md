# Description

🎯 This project is an AI agent for [OSHP](https://github.com/OWASP/www-project-secure-headers/) that tries to find any *HTTP response security header* that OSHP missed.

# Flow

🤖 The following schema show the flow followed by of the agent:

![flow](diagram.png)

# Agent pattern recommendation by Claude

```text
Given your goals (simple, educational, linear pipeline with an LLM validation step), the right pattern is a Sequential Pipeline Agent,
sometimes called a "Chain of Thought Pipeline" or just a multi-step chain.

Each step has a single responsibility and passes its output to the next step.
The only "agentic" decision point is the LLM filter + LLM validator pair.

[Data Fetcher] → [Header Merger] → [Direction Classifier] → [LLM Filter] → 
[LLM Validator] → [OSHP Diff] → [Report]
```
