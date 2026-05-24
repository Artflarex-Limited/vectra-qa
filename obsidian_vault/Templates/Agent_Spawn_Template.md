---
title: Agent Spawn Template
agent_role: "{{ROLE}}"
agent_id: "{{AGENT_ID}}"
parent_run: "{{RUN_ID}}"
status: spawned
objective: "{{OBJECTIVE}}"
spawned_at: "{{TIMESTAMP}}"
terminated_at: null
result: pending
compute_pid: null
---

# {{ROLE}} Agent Log

## Objective
{{OBJECTIVE}}

## Progress
- **Started**: {{TIMESTAMP}}
- **Last Action**: initialized
- **Status**: active

## Findings
_No findings recorded yet._

## Termination Criteria
- [ ] Objective completed
- [ ] Findings written to this node
- [ ] Parent node [[Test_Run_Master]] notified

## Wiki-Links
- [[Test_Run_Master]] - Parent test run
- [[UI_State_Log]] - UI testing context (if applicable)
- [[Data_Validation_Log]] - Data validation context (if applicable)
