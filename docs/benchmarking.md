# International benchmarking: five leading rail systems vs Malaysia

Compiled 2026-11-20. Companion to [literature_review.md](literature_review.md). Purpose: learn
how the best railways define, plan for and measure punctuality, compare that with KTMB ETS,
and change the study where the comparison shows a weakness.

"Checked" uses the same labels as the literature review: **Read** = the page was opened,
**Index** = search-engine summary only, confirm before citing.

---

## 1. Which five countries, and why

No single current ranking covers both quality and punctuality worldwide, so the choice
combines three kinds of evidence:

| Evidence | What it says | Checked |
| --- | --- | --- |
| WEF Global Competitiveness Report, railway quality indicator (last full edition 2019) | Top five: Japan, Hong Kong, Switzerland, South Korea, Singapore [B1] | Index |
| BCG European Railway Performance Index 2017 (latest edition) | Switzerland first (7.2/10), then Denmark, Finland, Germany, Austria [B2] | Index |
| Operator punctuality 2025 | SBB 94.1%, ÖBB 94.1%, NS 85.3% at 3 min, JR Central 1.4 min average delay per train (sections 2 to 6) | Read / Index |

Chosen: **Japan, Switzerland, Austria, the Netherlands and South Korea.**

- Hong Kong and Singapore are left out because their high scores come from urban metros,
  which are not comparable with a 900 km intercity corridor.
- Austria and the Netherlands are in instead of Denmark and Finland because they publish
  detailed 2025 punctuality and planning norms that the model can use.
- South Korea is the closest structural match to the ETS: one main intercity spine with
  fast-growing demand. It is also a warning case (section 6).

---

## 2. Japan (JR Central, Tokaido Shinkansen)

| Item | Value | Source | Checked |
| --- | --- | --- | --- |
| Average delay per train | 1.4 min FY2024; 1.6 min FY2023 | JR Central Integrated Report 2025 [J1]; JR Central "About the Shinkansen" [J2] | Index / Read |
| What it includes | Delays from natural disasters are included | [J2] | Read |
| Older figures | 24 s (FY2016, disaster delays excluded) | Nippon.com 2018 [J3] | Read |

What Japan does differently:

- **Measures average delay per train, not a pass/fail threshold.** This keeps every minute
  visible, including the large incidents a 5 min threshold hides.
- **Literature:** Kunisaki and Takeuchi (2025) reschedule after small delays with optimisation,
  computed in under a minute so control can react live (Quarterly Report of RTRI 66(1):44-50)
  [J4]. Older work explains Shinkansen punctuality through operating practice and
  rescheduling, and a way to plan enough buffer without cutting frequency [J5]. Tokyo
  commuter studies show knock-on delay growing from dwell-time overruns at high frequency [J6].
  These are older than 2024 and are cited as background.

## 3. Switzerland (SBB)

| Item | Value | Source | Checked |
| --- | --- | --- | --- |
| Passenger punctuality 2025 | 94.1% (record; 93.2% in 2024) | swissinfo / Keystone-SDA, 27 Jan 2026 [S1] | Read |
| Definition | Arrival less than 3 min late | SBB punctuality page [S2] (page refused automated fetch) | Index |
| Connection punctuality 2025 | 98.6% nationally | Press coverage of SBB results [S3] | Index |
| How (stated) | Timetable robustness work, turning late trains from Germany at the border and running Swiss replacement trains | [S1] | Read |

What Switzerland does differently:

- **An integrated clock-face timetable (Taktfahrplan)** with timed transfers at hub stations.
  The timetable is built round connections, so SBB also reports **connection punctuality**:
  the share of planned transfers passengers actually make.
- **Protects its own network from imported delay.** Late trains from abroad are turned at the
  border rather than allowed to spread delay inside Switzerland.
- **Literature:** ETH Zurich work on the clock-face system reports that simulated real-time
  rescheduling cut total delay by 53% to 78% [S4], and that the Rail 2000 timetable was more
  stable than the old one even with more trains [S5]. The 2017 Rastatt closure was used to
  measure delay propagation empirically across the Swiss network (Scientific Reports 2020)
  [S6].

## 4. Austria (ÖBB)

| Item | Value | Source | Checked |
| --- | --- | --- | --- |
| Passenger trains on time 2025 | 94.1% (93.6% in 2024) | ÖBB Annual Report 2025 [A1] | Index |
| Long-distance vs local | 81.6% long-distance, 94.8% local | [A1] | Index |
| Definition | Not stated on the punctuality page | ÖBB Pünktlichkeit [A2] | Read |
| How (stated) | Renewal of trains and infrastructure, priority for fast long-distance trains, works coordinated with neighbours | [A2] | Read |

What Austria does differently:

- **Reports long-distance and local separately.** Long-distance trains are 13 points less
  punctual, because a long run collects disturbances from many sections. The ETS is almost
  entirely long-distance (up to 900 km), so the right comparison for ETS is ÖBB long-distance
  81.6%, not the 94.1% headline.
- **Plans the network round an integrated timetable.** Zielnetz 2040 includes a node-edge
  model for the integrated clock-face timetable [A3].

## 5. The Netherlands (NS and ProRail)

| Item | Value | Source | Checked |
| --- | --- | --- | --- |
| Trains on time 2025 | 85.3% within 3 min; 95.2% within 10 min | NS year-end figures, IamExpat 19 Dec 2025 [N1] | Read |
| Threshold change | From 1 Jan 2025 NS reports 3 min (small delay) and 10 min (large), instead of 5 and 15 | [N2] | Index |
| ProRail main network 2025 | 85.5% at 3 min (floor 84.4%) | ProRail annual report 2025 to parliament [N3] | Index |
| Running time supplement | About 7% of technical minimum running time | ProRail planning norms as quoted by TU Delft [N4] | Index |
| Minimum headway buffer | 60 s on every headway (aim to cut to 30 s) | TU Delft studies [N4] | Index |

What the Netherlands does differently:

- **Writes its planning norms down.** A fixed running time supplement (about 7%) lets late
  trains recover; a fixed buffer on every headway (60 s) stops delay passing from one train
  to the next. Kroon et al. describe this trade-off in the design of the 2007 Dutch timetable
  [N5]: supplements absorb small delays, buffers stop propagation, both cost rolling stock.
- **Tightened its own definition.** Moving from 5 to 3 min made the headline number worse on
  purpose, to measure what passengers notice.
- **Literature:** absorption graphs for station routing, tested at Breda, Arnhem and
  Amersfoort, cut propagation compared with buffer-based methods (Public Transport, 2026)
  [N6]. Recent machine-learning work predicts delayed trajectories on the Dutch network
  (arXiv 2025, 2026) [N7]. Goverde's max-plus delay propagation (Transportation Research
  Part C, 2010) was built on Dutch timetables [F1].

## 6. South Korea (Korail KTX)

| Item | Value | Source | Checked |
| --- | --- | --- | --- |
| KTX trains more than 5 min late | 8.5% (2019), 7.5% (2020), 10.8% (2021), 17.6% (2022) | 2023 National Audit, Asia Economy [K1] | Index |
| Compensation | Paid for delays over 20 min | [K1] | Index |
| Load | KTX utilisation 110%, SRT 131% | Asia Economy, May 2026 [K2] | Index |

What Korea shows: **demand grew faster than capacity, and delay doubled in three years.**
That is the risk KTMB takes in 2027 when ETS goes from 44 to up to 58 trains a day on the same
track (literature review, Part A3).

## 7. International planning standards

| Standard | What it sets | Checked |
| --- | --- | --- |
| UIC 451-1 | Running time supplement = percentage of minimum running time plus a fixed allowance. For multiple units, as quoted by secondary sources: 3% up to 140 km/h, 4% at 141-160 km/h, plus about 1 min per 100 km [U1] | Index (confirm against the leaflet) |
| UIC 406 | Capacity consumption: compress the timetable to minimum headways, add buffer, compare with the time window. Published limits are in the order of 70-85% depending on line type [U2] | Index |

---

## 8. Malaysia compared

| Dimension | Best practice (sections 2-7) | KTMB ETS | Gap |
| --- | --- | --- | --- |
| On-time definition | Published: 3 min (SBB, NS), average delay per train (JR) | Not published (literature review, A2) | Results cannot be compared like for like |
| Unit measured | Trains, passengers and connections (SBB, NS) | Trains, festive periods only (86% CNY 2026, 95% Raya 2026) | No passenger or connection measure |
| Reporting | Annual, by region and service type (SBB, ÖBB) | Half-year disruption minutes, festive punctuality | No long-distance vs local split |
| Running time supplement | About 3-7% of minimum time (UIC 451-1, ProRail) | Implied 37% median against a 140 km/h constant-speed minimum (this study, below) | The model's minimum is too optimistic; see 9.2 |
| Headway buffer | 60 s minimum on every headway (ProRail) | 4.7% of same-direction departures from a station are under 5 min apart, including 0 min pairs | Same-minute pairs break any buffer rule |
| Timetable concept | Integrated clock-face with timed transfers (CH, AT) | Irregular; through trains split at KL Sentral from 2027 | Transfers will matter but are not planned or measured |
| Growth vs capacity | Korea: delays doubled when demand outran capacity | 44 to 58 trains a day on the same track in 2027 | Same risk |

---

## 9. What this changed in the study (done)

### 9.1 Punctuality at the benchmark thresholds

`metrics.benchmark_thresholds_min: [1, 3, 5, 10, 15]` in `config.yaml`. Every replication now
also reports on-time % at those thresholds, at destinations and at all stops
(`on_time_dest_3min_pct` and so on). The 5 min headline stays, but results can now be quoted
against SBB/NS (3 min) and NS large delay (10 min).

### 9.2 Benchmark-based recovery model

Finding: measured against a constant 140 km/h, the published ETS timetable holds a **median
37% running time supplement** per stop-to-stop section (mean 68%, lowest 6% Ipoh-Sungai Siput,
highest 705% on the 1.2 km Kuala Lumpur-KL Sentral hop) (`results/timetable_supplements.csv`).
Real railways plan 3-7%. The gap is not generosity in the timetable: acceleration, speed
limits, curves and shared track are not in the model, so the line-speed minimum is far too
fast, and v1 lets late trains win back far too much time.

New option `operations.recovery_model: supplement`: the minimum running time is the published
running time with a UIC 451-1 style supplement removed, never faster than line speed. The
minimum is fixed from the published timetable, so a buffer added later stays recoverable.

`python -m ets_sim.experiments --only benchmark`, 100 replications, 5 min threshold:

| Recovery model | Total slack | On time all stops | On time at destination (95% CI) | Dest. 3 min | Dest. 10 min | Avg dest. delay |
| --- | --- | --- | --- | --- | --- | --- |
| Line speed (v1) | 7,580 min | 93.3% | 86.8% (86.6-87.0) | 86.7% | 88.0% | 4.5 min |
| UIC 451-1, 3% + 1 min/100 km | 1,016 min | 88.9% | 79.3% (79.0-79.6) | 77.4% | 84.6% | 6.5 min |
| UIC 451-1, 4% + 1 min/100 km | 1,226 min | 89.4% | 79.6% (79.3-80.0) | 78.4% | 84.7% | 6.4 min |
| ProRail, 7% | 1,499 min | 90.0% | 80.1% (79.8-80.3) | 79.0% | 85.4% | 6.2 min |

- With realistic recovery, destination punctuality falls by about 7 points, to about 80%.
  That is close to the 80-86% KTMB reported for CNY 2025 and 2026, and to ÖBB long-distance
  (81.6%). This is a plausibility check, not validation: the primary delay inputs are still
  placeholders.
- `timetable_conflict` delay falls (945 to 513-558 min). A likely reason, not yet checked:
  with less recovery a late train stays late, so it splits a same-minute pair or tight
  follow-on instead of catching up into it (the same effect noted in the README for primary
  delays). Check before writing it in the report.

### 9.3 Buffer time matters once recovery is realistic

Buffer sweep, UIC 4% + 1 min/100 km, 100 replications:

| Buffer per journey | On time all stops | On time at destination (95% CI) | Avg dest. delay |
| --- | --- | --- | --- |
| 0 min | 89.4% | 79.7% (79.3-80.0) | 6.4 min |
| 2 min | 89.8% | 80.0% (79.8-80.3) | 6.3 min |
| 4 min | 90.2% | 80.3% (80.1-80.6) | 6.2 min |
| 6 min | 90.6% | 80.5% (80.3-80.8) | 6.1 min |

Under the line-speed model the same sweep is flat (README, "Findings so far"). So the v1
conclusion "buffer barely matters" came from the idealised slack, not from the railway.
The effect is still small because most remaining delay is timetable conflict, which extra
running time does not remove. This supports the Dutch point that headway buffers, not only
running supplements, are what stop propagation (section 5).

---

## 10. Further improvements (not done yet)

Ordered by value for the FYP.

| # | Improvement | From | Effort |
| --- | --- | --- | --- |
| 1 | **Make `supplement` the default recovery model and re-run every experiment.** Changes every number in the README. | UIC, ProRail | Small (config + re-run) |
| 2 | **Connection punctuality at KL Sentral** for the 2027 split through-services: share of planned transfers made, against a minimum transfer time (ASSUMPTION). | SBB | Medium |
| 3 | **Long-distance vs short trips** in the punctuality report (for example by journey length band). | ÖBB | Small |
| 4 | **Headway buffer rule:** flag scheduled headways below minimum headway + 60 s per section; UIC 406 capacity consumption for the busiest sections (Rawang-KL, KL-Seremban). | ProRail, UIC 406 | Medium |
| 5 | **Average delay per train including incidents** (JR style): combine normal days with replayed incident days into a yearly figure. | JR Central | Small after more replays |
| 6 | **Demand-growth stress test against the real 2027 plan** (50 and 58 trains a day) instead of generic synthetic trips. | Korea warning, KTMB 2027 plan | Medium |
| 7 | **Clock-face timetable scenario:** a regular-interval ETS timetable with the same number of trains, compared with the current one. | CH, AT | Large |

---

## References

- [B1] Statranker, Top 10 countries by railway quality (WEF data). https://statranker.org/economy/construction-infrastructure/top-10-countries-by-railway-quality/
- [B2] BCG, 2017 European Railway Performance Index. https://www.bcg.com/publications/2017/transportation-travel-tourism-2017-european-railway-performance-index.aspx
- [J1] JR Central Integrated Report 2025. https://global.jr-central.co.jp/en/company/ir/annualreport/_pdf/annualreport2025-13.pdf
- [J2] JR Central, About the Shinkansen. https://global.jr-central.co.jp/en/company/about_shinkansen
- [J3] Nippon.com, 25 May 2018, The Tokaido Shinkansen's world-class safety, reliability, and frequency. https://www.nippon.com/en/features/h00201
- [J4] Kunisaki, Takeuchi (2025). Quarterly Report of RTRI 66(1):44-50. https://www.jstage.jst.go.jp/article/rtriqr/66/1/66_rtriqr.66.1_44/_html/-char/en
- [J5] How the punctuality of the Shinkansen has been achieved. https://www.researchgate.net/publication/271420182
- [J6] Simulation analysis of train operation to recover knock-on delay under high-frequency intervals. https://www.sciencedirect.com/science/article/abs/pii/S2213624X14000418
- [S1] swissinfo.ch, 27 Jan 2026, Swiss Federal Railways reports record punctuality in 2025. https://www.swissinfo.ch/eng/swiss-politics/swiss-federal-railways-reports-record-punctuality-in-2025/90842888
- [S2] SBB, Punctuality. https://company.sbb.ch/en/company/responsibility/customers/punctuality.html
- [S3] Travelmole, Switzerland rail punctuality. https://travelmole.com/news/switzerland-rail-punctuality
- [S4] IVT ETH Zurich (2007), A new framework for railroad traffic control. https://archiv.ivt.ethz.ch/oev/publications/papers/2007A_ML.pdf
- [S5] Ullius (2005), Delay analysis of Rail 2000 1st phase using OpenTimeTable. https://archiv.ivt.ethz.ch/oev/publications/papers/2005_MU.pdf
- [S6] Empirical dynamics of railway delay propagation identified during the large-scale Rastatt disruption. Scientific Reports (2020). https://pmc.ncbi.nlm.nih.gov/articles/PMC7596077/
- [A1] ÖBB Annual Report 2025. https://static.web.oebb.at/bericht/2025/annual-report/35/
- [A2] ÖBB, Pünktlichkeit. https://www.oebb.at/de/rechtliches/puenktlichkeit
- [A3] Zielnetz 2040 Fachentwurf. https://www.bmk.gv.at/dam/jcr:ad67d636-a043-4314-862a-576af9fc5404/Zielnetz2040_Fachentwurf.pdf
- [N1] IamExpat, 19 Dec 2025, NS trains were on time more often in 2025. https://www.iamexpat.nl/expat-info/dutch-news/ns-trains-were-time-more-often-2025-problems-remain
- [N2] NS half-year figures 2025. https://www.fnv.nl/getmedia/7cd122ef-145a-40e0-987d-7a50f1478af3/Halfjaarcijfers-NS-2025-30-07-2025.pdf
- [N3] ProRail Jaarverantwoording 2025. https://www.eerstekamer.nl/nonav/overig/20260522/jaarverantwoording_2025_prorail/document
- [N4] TU Delft, Running time supplements: energy-efficient train control. https://repository.tudelft.nl/file/File_02a115ec-061e-4558-9c5c-1e6bd7a3ea37?preview=1
- [N5] Kroon et al., The new Dutch timetable: the OR revolution. https://repub.eur.nl/pub/13767/EI200819.pdf
- [N6] Absorption graphs for the timetable-constrained station routing problem. Public Transport (2026). https://link.springer.com/article/10.1007/s12469-026-00425-1
- [N7] Predicting delayed train trajectories on the Dutch railway network. https://arxiv.org/abs/2507.11776 and https://arxiv.org/abs/2609.34692v1
- [K1] Asia Economy, 17 Oct 2023, One in five KTX and SRT trains operate with delays. https://www.asiae.co.kr/en/article/2023101707565040947
- [K2] Asia Economy, 11 May 2026, KTX utilization reaches 110%, SRT hits 131%. https://www.asiae.co.kr/en/article/2026051116371435591
- [U1] Aalborg Trafikdage 2011 (Schittenhelm), UIC 451-1 supplement table. https://www.trafikdage.dk/papers_2011/63_BerndSchittenhelm.pdf
- [U2] UIC 406 (2013). https://tamannaei.iut.ac.ir/sites/tamannaei.iut.ac.ir/files/files_course/uic406_2013.pdf
- [F1] Goverde, R.M.P. (2010). Transportation Research Part C 18(3), 269-287.
