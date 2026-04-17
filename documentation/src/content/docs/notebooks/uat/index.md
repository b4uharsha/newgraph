---
title: "UAT Validation"
---

<div class="nb-header">
  <span class="nb-header__type">Index</span>
  <h1 class="nb-header__title">UAT Validation</h1>
  <p class="nb-header__subtitle">User Acceptance Testing for Graph OLAP platform</p>
</div>

This section contains the UAT validation notebook covering test cases GP-01 through GP-08 from the Graph OLAP UAT test plan. The notebook exercises the complete platform surface — SDK authentication, graph mapping, instance lifecycle, Cypher queries, graph algorithms, export, sharing, admin configuration, error handling, and resilience — in a single executable workflow.

<div class="nb-card-grid">
  <a href="01_uat_validation/" class="nb-card">
    <div class="nb-card__title">UAT Validation</div>
    <div class="nb-card__description">End-to-end validation of test cases GP-01 through GP-08</div>
    <div class="nb-card__meta">60 min · Advanced</div>
  </a>
</div>

<div class="nb-section">
  <span class="nb-section__number">✔</span>
  <div>
    <h2 class="nb-section__title">Test Case Coverage</h2>
    <p class="nb-section__description">GP-01 through GP-08 from the UAT test plan</p>
  </div>
</div>

| Test Case | Description | Role |
|-----------|-------------|------|
| GP-01 | E2E Workflow (Data Analyst) | Data Analyst |
| GP-02 | Invalid Mapping Validation | Data Analyst |
| GP-03 | E2E Workflow (Ops) | Ops |
| GP-04 | E2E Workflow (Admin) | Admin |
| GP-05 | Admin Platform Configuration | Admin |
| GP-06 | Non-Admin Access Denied | Data Analyst |
| GP-07 | Export Worker Resilience | Ops |
| GP-08 | Starburst Connectivity Loss | Data Analyst |

<div class="nb-navigation">
  <div class="nb-navigation__title">Related Tutorials</div>
  <div class="nb-card-grid">
    <a href="../04-admin-ops/" class="nb-card">
      <div class="nb-card__title">Administration & Operations</div>
      <div class="nb-card__description">Platform administration, monitoring, and maintenance</div>
      <div class="nb-card__meta">3 tutorials</div>
    </a>
    <a href="../05-advanced/" class="nb-card">
      <div class="nb-card__title">Advanced Topics</div>
      <div class="nb-card__description">Instance lifecycle, export pipelines, advanced mappings, and graph engines</div>
      <div class="nb-card__meta">5 tutorials</div>
    </a>
  </div>
</div>
