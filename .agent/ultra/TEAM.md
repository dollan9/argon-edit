# Active Agent Team & Delegation Roster

## 1. Active Orchestration Squad
| Agent Identifier | Role Title | System Prompt Type | Workspace Mode | Assigned Workstream |
| :--- | :--- | :--- | :--- | :--- |
| `orchestrator` | Lead Orchestrator | Root Agent | `inherit` | Global coordination |
| `sub-critic` | Adversarial Critic | `ultra-critic` | `inherit` | Blind review & security audit |
| `sub-builder` | Implementation Specialist | `ultra-builder` | `inherit` | Core implementation |
| `sub-tester` | QA & Verification Engineer | `ultra-tester` | `inherit` | Verification & testing |

## 2. Active Delegation Contracts
### Contract: `sub-builder`
- **Mission**: Implement core functionality according to PLAN.md
- **Target Files**: Specified in task assignment
- **Required Deliverable**: Working code with tests
- **Completion Trigger**: Clean build and unit test pass

### Contract: `sub-critic`
- **Mission**: Conduct blind adversarial critique of implementation diff
- **Required Deliverable**: Defect report (CRITICAL, HIGH, MEDIUM, LOW)

