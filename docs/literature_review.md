# Literature review and problem evidence

Compiled 2026-11-20. Purpose: give the FYP a problem statement backed by recent, credible
sources, and turn that evidence into experiments for RQ1 (propagation), RQ2 (bottlenecks)
and RQ3 (timetable resilience).

How to read the "Checked" column:

- **Read** - the article or abstract page was opened and the facts below come from it.
- **Index** - the facts come from a search engine summary only. Open the source and confirm
  before you cite it in the report.

---

## Part A - The problem in Malaysia (news and official figures, 2025-2026)

### A1. Incidents on the ETS corridor

| Date | Source | What happened | Delay reported | Checked |
| --- | --- | --- | --- | --- |
| 26-27 Sep 2026 | The Star / Bernama [N1] | Signalling component damage between Kalumpang and Kuala Kubu Bharu, during Rawang-Ipoh double-tracking works. KTMB said it had a "knock-on effect" on trains to and from the north. | ETS EP9138 (KL Sentral-Butterworth) 305 min, Komuter 2389 230 min, residual 30 min next day | Read |
| 14 Jun 2026 | Malay Mail / Bernama [N2] | Overhead line equipment outage at KM 458.872 between Tiroi and Seremban | Eight ETS trains late on KL Sentral-JB Sentral: EX9573 3 h 34 min, EG9442 2 h 51 min, EP9524 2 h 35 min, EP9323 2 h 11 min, EP9326 1 h 40 min, EG9343 1 h 14 min, EX9575 1 h, EP9428 25 min | Read |
| 18 Nov 2026 | NST [N3] | Cable theft knocked out signalling on the Bukit Mertajam line | Up to about 80 min, ETS and northern Komuter | Index |
| 23 Jul 2026 | SoyaCincau [N4] | Overhead power line failure between Batang Benar and Labu, linked to unauthorised third-party works | Not confirmed | Index |
| 26 May 2026 | The Star / Malaysian Reserve [N5] | Cable theft at KM 95.8, Sungai Siput-Kamunting | 23-40 min, northern services | Index |
| 23 Mar 2026 | Business Today [N6] | Technical failure at Rasa, Hulu Selangor | ETS EP9130 about 157 min | Index |

What this shows for the project:

1. **One fault reaches many trains.** The 14 Jun event is a ready-made RQ1 case: one
   section, one cause, eight named trains with recorded delays. The 26 Sep event shows a
   central-sector fault spreading north.
2. **Primary delays are mostly external, not the timetable.** Cable theft, overhead line
   faults, signalling faults and third-party works. The model should treat these as
   injected section outages, not just random running-time noise.
3. **Delays are hours, not minutes.** A model that only uses small stochastic dwell and
   running noise will not reproduce these events. Both a "daily noise" regime and a
   "major incident" regime are needed.

### A2. Official and ministry figures

| Figure | Source | Checked |
| --- | --- | --- |
| Cable theft caused 381 h of KTMB delays in 2025: **246 h ETS**, 135 h Komuter, 0 h Intercity. 432 KTMB cable theft cases from 2024 to Jun 2026. | Deputy Transport Minister in Dewan Negara, Malay Mail 3 Aug 2026 [N7] | Read |
| Earlier ministry figure: over 1,300 h of train delays from cable theft in 2025. Conflicts with the 381 h figure above (different scope or period). Do not use both without explaining. | FMT / Malay Mail, 20-21 Nov 2025 [N8] | Index |
| H1 2026 total disruption minutes 113,431, down 40% from 188,525 in H1 2025. CEO: punctuality now driven mainly by cable theft, third parties, floods, fallen trees, utility works. | Bernama, Jul 2026 [N9] | Index (Bernama refused connection) |
| ETS punctuality: 86% over CNY 2026 (80% in 2025), 95% over Aidilfitri 2026 (94% in 2025). | The Star 6 Mar 2026 [N10], Paul Tan 2 Apr 2026 [N11] | Index |
| KTMB has not published a full-year 2025 annual report with punctuality. Latest financial statements are to 31 Dec 2024. | The Star 31 Jul 2026 [N12] | Index |

Point for the report: KTMB publishes only aggregate and festive-period punctuality. There
is no public tool to ask "what if" questions about where delay spreads. That is the gap
this simulator fills.

### A3. Capacity is growing on the same track

| Change | Source | Checked |
| --- | --- | --- |
| ETS daily services 44 (2026) to 50 Mon-Thu and 58 Fri-Sun (2027). JB Sentral-KL Sentral 8 to 12 per day. 1,573,872 seats Jan-Mar 2027 (+39%). Old KL Station and Subang Jaya become extra ETS hubs to relieve KL Sentral. | Malay Mail 29 Oct 2026 [N13] | Read |
| From 1 Jan 2027, JB Sentral-Butterworth, JB Sentral-Padang Besar and Butterworth-Segamat stop running as through trains. Passengers change at KL Sentral. One trainset now covers several shorter trips. | The Star 2 Nov 2026 [N14] | Read |
| Gemas-JB electrified double track opened Dec 2025. KL-JB doubled to 8 trips from 1 Jan 2026. | Malay Mail 11 Dec 2025 [N15], SAYS [N16] | Index |
| Klang Valley Double Track Phase 2 runs on one operational track shared by Komuter, ETS and freight, with a nightly line block 21:30-05:30. Completion expected 2027. Minister: Seremban-KL Komuter trips of 1 h 45 min to 2 h. | The Star 20-21 May 2026 [N17], Paul Tan 16 Feb 2026 [N18] | Index |

What this shows for the project:

1. **More trains on the same infrastructure means less slack.** This is a direct RQ3
   question: does going from 44 to 58 daily trains raise knock-on delay per minute of
   primary delay?
2. **The route split creates a new failure mode: missed connections at KL Sentral.**
   Shorter trainset cycles also mean a late arrival can delay the same set's next trip.
   Neither appears in the current model and both are easy to add.
3. **Shared single-track working in the Klang Valley** is the strongest reason the v1
   "ETS only, double track" scope will understate delay there. State it as a limitation
   (see decision 3 in `docs/decisions.md`) and, if time allows, add a single-track section
   as a scenario.

---

## Part B - Academic literature

### B1. Delay propagation (RQ1)

| Ref | Year | What it does | Useful for us | Checked |
| --- | --- | --- | --- | --- |
| Elliker, Read, Vanier, Bifet. *Simulation-Driven Railway Delay Prediction: An Imitation Learning Approach*. AAAI-26 Main Track. arXiv:2512.19737 [A1] | 2025 | Treats delay forecasting as a stochastic simulation, learned from 3M+ Belgian train movements, with Monte Carlo runs for uncertainty. Argues rule-based simulators (RailSys, OpenTrack, PROTON) often miss real delay patterns on busy networks. | Supports Monte Carlo replications and reporting a distribution, not one number. Its criticism of rule-based tools is a limitation to state honestly, and a reason the realtime logger matters. Open code exists. | Read |
| Nguyen, Li. *Deep Learning to Identify the Spatio-Temporal Cascading Effects of Train Delays in a High-Density Network*. SIGSPATIAL 2025 GeoAI workshop. arXiv:2510.09350 [A2] | 2025 | Models the railway as a graph of events (arrivals, departures) with running, dwell and headway edges; GATv2 on Dutch data. A simple persistence baseline beat it on MAE. | The event graph (running / dwell / headway edges) matches our delay ledger causes. The baseline result is a useful warning: simple models can be competitive. | Read |
| Elliker, Le Bail, Mantoux, Read, Vanier. *RIDE: An Open Dataset and Benchmark for Train Delay Prediction*. arXiv:2606.05070 [A3] | 2026 | Open Belgian dataset, 2023-2025, 94.5M train events, with a standard evaluation protocol. | Shows the field is moving to open, reproducible data. Our pinned GTFS snapshot and seeded replications fit that direction. Possible source of realistic delay distributions. | Read |
| Tan, Remenyte-Prescott, Prescott, Culley. *Practical predictive model for evaluating performance and delay propagation in multi-track railways during disruptions*. Proc. IMechE Part F, doi:10.1177/09544097251344652 [A4] | 2025 | Real-time predictive model of operations during disruptions on UK multi-track lines. | Closest in spirit to our disruption scenarios. | Index (publisher blocked fetch) |
| Traffic-driven SIS epidemic model of high-speed rail delay propagation. Int. J. Modern Physics C 36(7) [A5] | 2025 | Delay spreads like an infection, driven by traffic frequency. | Alternative framing for the "how many trains does one delay reach" metric. | Index |
| Goverde. *A delay propagation algorithm for large-scale railway traffic networks*. Transportation Research Part C 18(3) [F1] | 2010 | Max-plus based propagation of initial delays through a timetable. | Foundational. Cite as the classical method our DES approximates. | Foundational |
| Meester, Muns. *Stochastic delay propagation in railway networks and phase-type distributions*. Transportation Research Part B 41(2) [F2] | 2007 | Analytical delay distributions through a network. | Foundational. | Foundational |
| Dekker et al. *Modelling railway delay propagation as diffusion-like spreading*. EPJ Data Science [F3] | 2022 | Diffusion model on Belgian data; spatial aggregation helps. | Supports reporting delay by section, not only by train. | Index |

### B2. Timetable robustness and buffer time (RQ3)

| Ref | Year | What it does | Useful for us | Checked |
| --- | --- | --- | --- | --- |
| Correia Duarte, Dauzere-Peres, Huisman, Mannino, Sartor, Weik, Widmann (author list differs slightly between repositories). *50 years of OR in railway timetabling and rolling stock planning*. EURO J. Transportation and Logistics 14, 100155, doi:10.1016/j.ejtl.2025.100155 [A6] | 2025 | Survey. Buffer times are the standard robustness tool; deciding their size and **location** is the main problem. | Strong citation for RQ3. Motivates comparing uniform buffers against buffers placed at the bottlenecks found in RQ2. | Index (PDF downloaded, text not extracted) |
| *Reconfiguring the planned railway timetable with robustness against disturbances*. Int. J. Rail Transportation, doi:10.1080/23248378.2026.2654033 [A7] | 2026 | Robustness indicators under stochastic disturbances, iterative timetable reconfiguration, checked in OpenTrack. | Same loop as our RQ3: change the timetable, re-run the stochastic model, compare. | Index (publisher blocked fetch) |
| *Extending robustness concepts ... station routing problem using absorption graphs*. Public Transport, doi:10.1007/s12469-026-00425-1 [A8] | 2026 | Argues buffer-based robustness ignores where the buffer sits in the timetable. | Same point as A6, from a station angle. | Index |
| Buffer time distributions in delay propagation modelling (RWTH Aachen) [F4] | n.d. | Stochastic event-based simulation; centred buffer time distributions give more stable results. | Guides how to spread added buffer. | Index |

### B3. Resilience after a disruption (RQ1 and RQ3)

| Ref | Year | What it does | Useful for us | Checked |
| --- | --- | --- | --- | --- |
| Li, Huang. Resilience quantification of high-speed railway train diagram under operation section interference. Reliability Engineering & System Safety [A9] | 2025 | Structure analysis, disruption impact, process simulation, resilience assessment. | Template for a "time to recover" metric after an injected section outage. | Index |
| Resilience assessment of high-speed railway networks, Jiangsu case. RESS 259, 110900 [A10] | 2025 | Timetable-based model of infrastructure plus operations; resilience as vulnerability plus reliability. | Supports measuring both how far service drops and how fast it recovers. | Index |

### B4. Dwell time variability (model inputs)

| Ref | Year | What it does | Useful for us | Checked |
| --- | --- | --- | --- | --- |
| Statistical dwell time models on regional rail. Sustainability 17(24), 10968 [A11] | 2025 | Passenger-flow time is predictable (R2 about 0.65) but total dwell is not (R2 about 0.25); door cycles and conductor procedures drive the rest. | Justifies a stochastic dwell distribution rather than a fixed or passenger-driven dwell. | Index |
| Baali, Buisson, Coulaud, Daamen. Boarding and alighting as a Markov process. Physica A [A12] | 2025 | Distributions of boarding and alighting time. | Background for the dwell assumption. | Index |

### B5. Bottlenecks (RQ2)

| Ref | Year | What it does | Useful for us | Checked |
| --- | --- | --- | --- | --- |
| Identifying service-oriented capacity bottlenecks in high-speed railways under disruption. Springer conference chapter, doi:10.1007/978-981-92-2250-6_44 [A13] | 2026 | Ranks bottlenecks by service impact, not train frequency. Beijing-Shanghai case. | Supports ranking sections by secondary delay caused, which is what our delay ledger does. | Index |
| Identification of critical track sections in a railway station using a multiplex network approach. Mathematics 13(7), 1151 [A14] | 2025 | Static occupancy-based critical sections. | Contrast: static occupancy vs our dynamic secondary-delay ranking. | Index |

### B6. Prior Malaysian work

| Ref | Year | What it does | Checked |
| --- | --- | --- | --- |
| Punctuality of intercity trains and passengers' perspective towards arrival time delay. Res. J. Applied Sciences, Eng. and Technology 11(9):1998-2002 [M1] | about 2015 (confirm) | Observation and survey of KTMB intercity punctuality at Kluang. Describes itself as possibly the first such Malaysian paper. | Index |
| Mixed integer programming to reduce delay, Padang Besar-Sungai Petani Komuter. UTM Proc. Science and Mathematics vol. 3 [M2] | 2021 | Optimisation of the timetable, not simulation. | Index |
| User perceptions of KTM Komuter, Planning Malaysia [M3] | about 2013 | Survey: about 3 in 4 users experienced delays. | Index |

---

## Part C - Gap this project fills

1. **No published simulation study of the ETS corridor.** Malaysian work found is surveys,
   station observation, or optimisation, and is 5-13 years old (B6). None covers the
   post-December 2025 corridor with Gemas-JB in service.
2. **Recent international work is mostly machine learning prediction on dense European
   networks** (A1-A3). It needs years of train-event data that KTMB does not publish.
   A macroscopic DES driven by public GTFS is a practical alternative where data is scarce.
3. **Buffer location matters more than buffer size** (A6, A8), but no study tests this
   for a long Malaysian corridor. RQ2 output (bottleneck ranking) feeds directly into an
   RQ3 experiment on targeted buffers.
4. **Operational changes in 2027** (more trains, broken through-services, shorter trainset
   cycles) have no published impact assessment (A3 in Part A).

Draft problem statement:

> KTMB ETS services suffered multi-hour, multi-train delays in 2026 from single-section
> faults (signalling, overhead line, cable theft), with 246 hours of ETS delay from cable
> theft alone in 2025. KTMB plans to raise ETS frequency from 44 to up to 58 trains a day
> in 2027 on the same infrastructure, yet there is no public, reproducible tool to show how
> a primary delay spreads along the corridor, which sections generate the most knock-on
> delay, or how much timetable buffer the denser service needs.

---

## Part D - Ideas to build from this

Ordered by value for effort. Each one maps to a research question.

| # | Idea | RQ | What to build | Evidence |
| --- | --- | --- | --- | --- |
| 1 | **Replay the 14 Jun 2026 Tiroi-Seremban outage** (done, see README) | RQ1, validation | Block the Tiroi-Seremban sub-blocks for N minutes from a start time; compare simulated delays of the eight trains with the reported ones. Calibrate N. | N2 |
| 2 | **Replay the 26 Sep 2026 Kalumpang-KKB signalling fault** | RQ1 | Same mechanism; count trains reached and how far north delay travels. | N1 |
| 3 | **Section outage as an incident type** (done) | RQ1 | Add a `section_outage` event (section, start, duration) to config, separate from small stochastic delays. | N1-N6, N9 |
| 4 | **Secondary-to-primary delay ratio** | RQ1 | One headline number: minutes of knock-on per minute of injected delay. Common in the literature and easy from the ledger. | A2, F1 |
| 5 | **2026 vs 2027 frequency** | RQ3 | Scale trip count from 44 to 50 and 58 per day (synthetic trips), measure OTP and the ratio from idea 4. | N13 |
| 6 | **Targeted vs uniform buffer** | RQ2 to RQ3 | Same total buffer minutes, spread evenly vs placed at the top RQ2 sections. | A6, A8 |
| 7 | **Missed connections at KL Sentral** | RQ3 | For split JB-Butterworth journeys, count passengers' connections missed vs transfer time. | N14 |
| 8 | **Trainset turnaround** | RQ1 | Link trips that share a trainset so a late arrival delays the next departure. Needs a trainset roster (ASSUMPTION or from realtime `vehicle.label`). | N14, decision 8 |
| 9 | **Recovery time metric** | RQ3 | Time from incident end until OTP returns to baseline. | A9, A10 |
| 10 | **Two delay regimes** | model input | Small stochastic dwell and running noise every run, plus rare large outages drawn from a frequency calibrated loosely on N7 and N9. | A11, N7, N9 |
| 11 | **Klang Valley single-track scenario** | limitation | One scenario where KL Sentral-Seremban behaves as single track, to show how much v1 understates delay. | N17, N18 |

Suggested first step: ideas 3 and 1 together. They give the report a real Malaysian
validation case, and the rest build on the section outage mechanism.

---

## References

News and official (Malaysia)

- [N1] The Star / Bernama, 27 Sep 2026. Signalling disruption causes up to five-hour delays for KTM Komuter, ETS. https://www.thestar.com.my/news/nation/2026/09/27/signalling-disruption-causes-up-to-five-hour-delays-for-ktm-komuter-ets
- [N2] Malay Mail / Bernama, 14 Jun 2026. ETS back on track after power outage, but eight services running late. https://www.malaymail.com/news/malaysia/2026/06/14/ets-back-on-track-after-power-outage-but-eight-services-running-late/223777
- [N3] NST, Nov 2026. Cable theft disrupts services on busy northern rail route. https://www.nst.com.my/news/nation/2026/11/1581062/cable-theft-disrupts-services-busy-northern-rail-route
- [N4] SoyaCincau, 23 Jul 2026. KTM Komuter and ETS disrupted today. https://soyacincau.com/2026/07/23/ktm-komuter-and-ets-disrupted-today-here-is-whats-causing-the-train-delays/
- [N5] The Star, 26 May 2026. Cable theft disrupts northern sector ETS and KTM Komuter services. https://www.thestar.com.my/news/nation/2026/05/26/cable-theft-disrupts-northern-sector-ets-and-ktm-komuter-services
- [N6] Business Today, 23 Mar 2026. KTM's Butterworth-bound ETS causes frustration after 2-hour delay. https://www.businesstoday.com.my/2026/03/23/ktms-butterworth-bound-ets-causes-frustration-after-2-hour-delay/
- [N7] Malay Mail, 3 Aug 2026. Rail cable theft costs Malaysia RM50m since 2024, causes 381 hours of KTMB delays. https://www.malaymail.com/news/malaysia/2026/08/03/deputy-transport-minister-rail-cable-theft-costs-malaysia-rm50m-since-2024-causes-381-hours-of-ktmb-delays/230075
- [N8] Free Malaysia Today, 20 Nov 2025. Cable thefts cause over 1,300 hours of train delays. https://www.freemalaysiatoday.com/category/nation/2025/11/20/cable-thefts-cause-over-1300-hours-of-train-delays-says-transport-ministry
- [N9] Bernama, Jul 2026. KTMB H1 2026 results. https://www.bernama.com/en/general/news.php?id=2588251
- [N10] The Star, 6 Mar 2026. KTMB records 72% surge in ETS passengers over CNY period. https://www.thestar.com.my/news/nation/2026/03/06/ktmb-records-72-surge-in-ets-passengers-over-cny-period
- [N11] Paul Tan, 2 Apr 2026. Perkhidmatan ETS catat peningkatan penumpang 109%. https://paultan.org/2026/04/02/perkhidmatan-ets-catat-peningkatan-penumpang-109-tren-intercity-49-sepanjang-aidilfitri-tahun-ini/
- [N12] The Star, 31 Jul 2026. New CEO on a mission to make KTM sustainable. https://www.thestar.com.my/news/nation/2026/07/31/new-ceo-on-a-mission-to-make-ktm-sustainable
- [N13] Malay Mail / Bernama, 29 Oct 2026. KTMB offers record 1.57 million ETS, ERT seats for January to March 2027. https://www.malaymail.com/news/malaysia/2026/10/29/ktmb-offers-record-157-million-ets-ert-seats-for-january-to-march-2027/241136
- [N14] The Star, 2 Nov 2026. KTMB restructures ETS routes to boost frequency, seat capacity. https://www.thestar.com.my/news/nation/2026/11/02/ktmb-restructures-ets-routes-to-boost-frequency-seat-capacity
- [N15] Malay Mail, 11 Dec 2025. KL-JB electric train to run four times daily starting January. https://malaymail.com/news/malaysia/2025/12/11/kljb-electric-train-to-run-four-times-daily-starting-january-boost-for-cny-and-hari-raya-travel/201563
- [N16] SAYS. KTMB doubles KL-JB ETS trips to 8 daily starting 2026. https://says.com/my/news/ktmb-doubles-kl-jb-ets-trips-to-8-daily-starting-2026
- [N17] The Star, 20 May 2026. KVDT2 upgrade expected to be completed two years ahead of schedule. https://www.thestar.com.my/news/nation/2026/05/20/kvdt2-upgrade-expected-to-be-completed-two-years-ahead-of-schedule-says-ktmb
- [N18] Paul Tan, 16 Feb 2026. KTM Komuter KL-Seremban schedules to be revised. https://paultan.org/2026/02/16/ktm-komuter-kl-seremban-schedules-to-be-revised-soon-to-cut-waiting-times-shorten-journeys-loke/

Academic

- [A1] https://arxiv.org/abs/2512.19737
- [A2] https://arxiv.org/abs/2510.09350
- [A3] https://arxiv.org/abs/2606.05070
- [A4] https://doi.org/10.1177/09544097251344652
- [A5] https://ideas.repec.org/a/wsi/ijmpcx/v36y2025i07ns0129183124502486.html
- [A6] https://doi.org/10.1016/j.ejtl.2025.100155 (open PDF: https://elib.dlr.de/217421/1/50-years-of-OR-in-railway-timetabling-and-rolling-stock-planning.pdf)
- [A7] https://www.tandfonline.com/doi/abs/10.1080/23248378.2026.2654033
- [A8] https://link.springer.com/article/10.1007/s12469-026-00425-1
- [A9] https://www.researchgate.net/publication/389790489
- [A10] https://www.sciencedirect.com/science/article/abs/pii/S0951832025001036
- [A11] https://www.mdpi.com/2071-1050/17/24/10968
- [A12] Baali et al., Physica A, 2025 (find DOI before citing)
- [A13] https://link.springer.com/chapter/10.1007/978-981-92-2250-6_44
- [A14] https://doi.org/10.3390/math13071151
- [F1] Goverde, R.M.P. (2010). Transportation Research Part C 18(3), 269-287.
- [F2] Meester, L.E., Muns, S. (2007). Transportation Research Part B 41(2), 218-230.
- [F3] https://link.springer.com/article/10.1140/epjds/s13688-022-00359-1
- [F4] https://publications.rwth-aachen.de/record/750797/files/750797.pdf
- [M1] https://www.researchgate.net/publication/290634309
- [M2] https://science.utm.my/procscimath/wp-content/uploads/sites/605/2021/11/18-24-Nur-Amalin-Naquiah_Nur-Arina-Bazilah-Aziz.pdf
- [M3] https://pdfs.semanticscholar.org/2624/c5440289adbf77b88b4909a82c24308fb278.pdf
