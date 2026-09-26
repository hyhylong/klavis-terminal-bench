# Durable ledger candidate implementation plan

- [x] Preserve v1 code and successful model evidence in Git (`89fb5d8`).
- [x] Research primary sources and state limits of extrapolating old model results.
- [x] Define the public store/filesystem contract and independent verifier boundary.
- [x] Implement trusted durable filesystem simulator with hand-computed crash tests.
- [x] Implement correct persistent replay baseline and an incremental store, with semantic differential tests.
- [x] Build realistic correction/lookup workload; calibrate and publish a 3-second median contract with measured headroom.
- [x] Build the unprivileged socket worker and trusted controller; check malicious submissions cannot write rewards or read expected answers in the tested boundary.
- [x] Construct a coherent broken starter, publish its storage/API contract and regression examples, and package the candidate. Difficulty remains unproven pending model trials.
- [ ] Run static/container/oracle/nop/review checks, then model pilots and full accepted-version evaluations.
- [ ] Incorporate real author metadata and human sections; prepare requested GitHub delivery only with complete evidence.
