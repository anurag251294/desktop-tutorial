# Hydro One SharePoint Migration - Phased Migration Plan

## Project Overview

| Attribute | Value |
|-----------|-------|
| Client | Hydro One |
| Data Volume | ~25 TB |
| Source | SharePoint Online |
| Destination | Azure Data Lake Storage Gen2 |
| Urgency | High (SharePoint storage at capacity) |
| Timeline | 10 weeks |

---

## Phased Approach

### Phase 1: POC Validation (Week 1)

**Objective:** Validate migration approach with 1-2 small libraries

| Task | Owner | Duration | Deliverable |
|------|-------|----------|-------------|
| Deploy Azure resources (dev) | PwC | 1 day | Resource group deployed |
| Register SharePoint app | PwC | 0.5 day | App with admin consent |
| Deploy ADF pipelines | PwC | 1 day | Pipelines deployed |
| Initialize control database | PwC | 0.5 day | Tables created |
| Enumerate 2 test libraries | PwC | 0.5 day | Control table populated |
| Run POC migration | PwC | 1 day | Files migrated to ADLS |
| Validate POC results | PwC/Hydro One | 1 day | Validation report |
| POC sign-off | Hydro One | 0.5 day | Approval to proceed |

**Success Criteria:**
- [ ] All files from test libraries migrated successfully
- [ ] File count matches 100%
- [ ] Files are accessible in ADLS
- [ ] Folder structure preserved
- [ ] No errors in audit log

**Exit Criteria:**
- [ ] POC sign-off obtained
- [ ] Issues documented and resolved
- [ ] Go/No-Go decision for Phase 2

---

### Phase 2: Pilot Migration (Week 2-3)

**Objective:** Migrate ~1 TB across multiple libraries to validate at scale

| Task | Owner | Duration | Deliverable |
|------|-------|----------|-------------|
| Enumerate all pilot libraries | PwC | 1 day | Full inventory |
| Configure production parameters | PwC | 0.5 day | Optimized settings |
| Execute pilot migration (batch 1) | PwC | 2 days | 500 GB migrated |
| Monitor and tune | PwC | Ongoing | Performance metrics |
| Execute pilot migration (batch 2) | PwC | 2 days | 500 GB migrated |
| Validate pilot results | PwC/Hydro One | 2 days | Validation report |
| Document lessons learned | PwC | 1 day | Lessons learned doc |
| Pilot sign-off | Hydro One | 0.5 day | Approval for bulk |

**Pilot Scope:**
- 10-20 document libraries
- Mix of sizes (small, medium, large)
- Mix of file types (documents, images, etc.)
- Total: ~1 TB

**Success Criteria:**
- [ ] 1 TB migrated successfully
- [ ] <5% failed files (all recoverable)
- [ ] Throughput >50 GB/day achieved
- [ ] Throttling managed effectively
- [ ] No data loss

---

### Phase 3: Bulk Migration (Week 4-8)

**Objective:** Migrate remaining 24 TB in batches of 2-5 TB

#### Week 4-5: Batch 1 (5 TB)
| Day | Activity | Volume |
|-----|----------|--------|
| Mon-Tue | Migrate small libraries (<100 MB) | 0.5 TB |
| Wed-Thu | Migrate medium libraries (100 MB - 1 GB) | 1.5 TB |
| Fri-Sun | Migrate large libraries (1-10 GB) | 3 TB |

#### Week 5-6: Batch 2 (5 TB)
| Day | Activity | Volume |
|-----|----------|--------|
| Mon-Tue | Migrate remaining medium libraries | 2 TB |
| Wed-Sun | Migrate large libraries | 3 TB |

#### Week 6-7: Batch 3 (7 TB)
| Day | Activity | Volume |
|-----|----------|--------|
| Mon-Sun | Migrate largest libraries (>10 GB) | 7 TB |

#### Week 7-8: Batch 4 (7 TB)
| Day | Activity | Volume |
|-----|----------|--------|
| Mon-Sun | Migrate remaining libraries | 7 TB |
| Thu-Fri | Retry failed items | Variable |
| Weekend | Final cleanup | Variable |

**Daily Schedule (Bulk Migration):**
| Time (EST) | Activity |
|------------|----------|
| 8:00 PM | Start evening batch |
| 8:00 AM | Review overnight results |
| 9:00 AM | Address failures |
| 5:00 PM | Prepare next batch |
| 8:00 PM | Start next batch |

**Weekly Checkpoints:**
- Monday: Review weekend progress
- Wednesday: Mid-week status meeting
- Friday: Weekly status report

---

### Phase 4: Validation & Cutover (Week 9-10)

**Objective:** Validate all migrated data and transition to production state

#### Week 9: Validation
| Task | Owner | Duration | Deliverable |
|------|-------|----------|-------------|
| Run validation pipeline | PwC | 1 day | Validation results |
| Address discrepancies | PwC | 2 days | Issues resolved |
| Generate final report | PwC | 1 day | Migration report |
| Business validation | Hydro One | 2 days | Business sign-off |

#### Week 10: Cutover
| Task | Owner | Duration | Deliverable |
|------|-------|----------|-------------|
| Enable incremental sync | PwC | 0.5 day | Sync running |
| Update documentation | PwC | 1 day | Updated runbook |
| Knowledge transfer | PwC | 2 days | Training complete |
| Handoff to sustainment | PwC/Hydro One | 1 day | Handoff complete |
| Final sign-off | Hydro One | 0.5 day | Project closure |

---

### Phase 5: Incremental Sync & Monitoring (Ongoing)

**Objective:** Maintain synchronization and monitor for issues

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Incremental sync | Daily (2 AM EST) | Automated |
| Monitor sync results | Daily | Hydro One |
| Weekly health check | Weekly | Hydro One |
| Monthly reporting | Monthly | Hydro One |
| Quarterly review | Quarterly | PwC/Hydro One |

---

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|----|------|------------|--------|------------|-------|
| R1 | SharePoint throttling delays migration | High | Medium | Off-peak scheduling, Microsoft engagement | PwC |
| R2 | Large files (>10 GB) fail to migrate | Medium | Low | Individual handling, increased timeout | PwC |
| R3 | API permissions revoked during migration | Low | High | Regular monitoring, backup credentials | PwC |
| R4 | SharePoint service outage | Low | High | Built-in retry, pause capability | N/A |
| R5 | Data corruption during transfer | Low | High | Checksum validation, source unchanged | PwC |
| R6 | ADLS storage capacity exceeded | Low | Medium | Capacity monitoring, alerts | PwC |
| R7 | Key personnel unavailable | Medium | Medium | Cross-training, documentation | Both |
| R8 | Business content changes during migration | Medium | Low | Incremental sync, re-migration capability | PwC |
| R9 | Network bandwidth insufficient | Low | Medium | Off-peak scheduling, bandwidth monitoring | Hydro One |
| R10 | Regulatory/compliance issues | Low | High | Early legal review, audit logging | Hydro One |

### Risk Response Plan

**R1 - SharePoint Throttling:**
- Primary: Run migrations during off-peak hours (8 PM - 6 AM EST)
- Secondary: Request throttling limit increase from Microsoft
- Tertiary: Reduce parallelism and extend timeline

**R5 - Data Corruption:**
- Primary: File count and size validation post-migration
- Secondary: Checksum validation for sampled files
- Tertiary: Re-migrate from source (data unchanged)

---

## RACI Matrix

| Activity | Hydro One IT | Hydro One Business | PwC | Microsoft |
|----------|-------------|-------------------|-----|-----------|
| Azure subscription setup | A/R | I | C | - |
| SharePoint admin consent | A/R | I | C | - |
| ADF deployment | A | I | R | - |
| Migration execution | A | I | R | - |
| Monitoring | A | I | R | - |
| Business validation | I | A/R | C | - |
| Throttling escalation | I | I | R | A |
| Knowledge transfer | A/R | I | R | - |
| Ongoing maintenance | R | I | C | - |

**Legend:** R = Responsible, A = Accountable, C = Consulted, I = Informed

---

## Resource Requirements

### PwC Team
| Role | FTE | Duration |
|------|-----|----------|
| Azure Data Engineer (Lead) | 1 | 10 weeks |
| Azure Data Engineer | 1 | 8 weeks |
| Project Manager | 0.5 | 10 weeks |

### Hydro One Team
| Role | FTE | Duration |
|------|-----|----------|
| SharePoint Administrator | 0.25 | 10 weeks |
| IT Project Manager | 0.5 | 10 weeks |
| Business Stakeholder | 0.1 | 2 weeks |

### Azure Resources
| Resource | Specification | Monthly Cost (Est.) |
|----------|---------------|---------------------|
| ADLS Gen2 | 30 TB, Hot tier | $600 |
| Azure Data Factory | Pay-as-you-go | $100-200 |
| Azure SQL | S1 Standard | $30 |
| Key Vault | Standard | $5 |
| **Total** | | **~$800-850/month** |

---

## Timeline Summary

```
Week 1  |████████| Phase 1: POC Validation
Week 2  |████████| Phase 2: Pilot Migration (1 TB)
Week 3  |████████| Phase 2: Pilot Migration (continued)
Week 4  |████████| Phase 3: Bulk Migration - Batch 1 (5 TB)
Week 5  |████████| Phase 3: Bulk Migration - Batch 2 (5 TB)
Week 6  |████████| Phase 3: Bulk Migration - Batch 3 (7 TB)
Week 7  |████████| Phase 3: Bulk Migration - Batch 4 (7 TB)
Week 8  |████████| Phase 3: Bulk Migration - Cleanup
Week 9  |████████| Phase 4: Validation
Week 10 |████████| Phase 4: Cutover & Handoff
```

---

## Key Milestones

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| M1: POC Complete | Week 1 | Pending |
| M2: Pilot Complete (1 TB) | Week 3 | Pending |
| M3: 50% Migration Complete (12.5 TB) | Week 6 | Pending |
| M4: Bulk Migration Complete (25 TB) | Week 8 | Pending |
| M5: Validation Complete | Week 9 | Pending |
| M6: Project Handoff | Week 10 | Pending |

---

## Assumptions

1. SharePoint Online service remains available during migration window
2. Network bandwidth is sufficient for estimated throughput
3. Microsoft will provide throttling relief if requested
4. Business stakeholders available for validation during Week 9
5. No major changes to source content during migration
6. Azure subscription has sufficient quota

## Dependencies

1. Azure AD app registration requires Global Administrator
2. SharePoint admin consent required before migration
3. Microsoft TAM engagement for throttling limit increase
4. Hydro One IT approval for Azure resource deployment
5. Business owner sign-off required at each phase

---

## Communication Plan

| Meeting | Frequency | Attendees | Purpose |
|---------|-----------|-----------|---------|
| Daily Standup | Daily | PwC Team | Progress updates |
| Status Meeting | Weekly | PwC, Hydro One IT | Weekly progress |
| Steering Committee | Bi-weekly | All stakeholders | Executive updates |
| Issue Escalation | As needed | Relevant parties | Issue resolution |

### Status Report Template

```
HYDRO ONE SHAREPOINT MIGRATION - WEEKLY STATUS REPORT
Week: [X] of 10
Date: [YYYY-MM-DD]

SUMMARY:
[1-2 sentence summary]

PROGRESS:
- Libraries Completed: XX / XXX (XX%)
- Data Migrated: XX TB / 25 TB (XX%)
- Files Migrated: XXX,XXX

THIS WEEK:
- [Accomplishment 1]
- [Accomplishment 2]

NEXT WEEK:
- [Plan 1]
- [Plan 2]

RISKS/ISSUES:
- [Risk/Issue and status]

DECISIONS NEEDED:
- [Decision required]
```

---

## Appendix: Detailed Week-by-Week Plan

### Week 1 - POC Validation

| Day | Task | Hours | Owner |
|-----|------|-------|-------|
| Mon | Deploy Azure resources | 4 | PwC |
| Mon | Register SharePoint app | 2 | PwC |
| Tue | Deploy ADF pipelines | 6 | PwC |
| Wed | Initialize SQL database | 2 | PwC |
| Wed | Enumerate test libraries | 2 | PwC |
| Wed | Run POC migration | 4 | PwC |
| Thu | Monitor and troubleshoot | 6 | PwC |
| Fri | Validate results | 4 | PwC |
| Fri | POC sign-off meeting | 2 | All |

### Week 2-3 - Pilot Migration

*Detailed task breakdown similar to Week 1...*

### Week 4-8 - Bulk Migration

*Migration batches scheduled by library size and priority...*
