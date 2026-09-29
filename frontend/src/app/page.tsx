"use client";

import React, { useState, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Stats {
  total_standards: number;
  verified_count: number;
  by_product_group: Record<string, number>;
}

interface AlliedStandard {
  relation_type: string;
  is_number: string;
  part: string | null;
  title: string;
}

interface StandardResult {
  id: number;
  is_number: string;
  part: string | null;
  title: string;
  scope_summary: string;
  product_group: string;
  category: string;
  status: string;
  latest_edition_year: number | null;
  amendment_count: number;
  superseded_by: {
    is_number: string;
    part: string | null;
    title: string;
  } | null;
  allied_standards: AlliedStandard[];
  certification: {
    status: string;
    order_reference?: string;
    note?: string;
  };
  source_url: string | null;
  verification_status: string;
  confidence: number;
  why_it_applies?: string;
}

interface RecommendResponse {
  query_id: number;
  language: string;
  results: StandardResult[];
  abstain: boolean;
  message: string;
  warnings: string[];
}

interface CitationResponse {
  valid_format: boolean;
  found: boolean;
  cited: {
    is_number: string;
    part: string | null;
    year: number | null;
  };
  standard: {
    title: string;
    status: string;
    latest_edition_year: number | null;
  } | null;
  verdict: string;
  messages: string[];
  available_parts?: string[];
}

interface ReviewItem {
  id: number;
  query_id: number;
  query_text: string;
  standard_id: number;
  is_number: string;
  part: string | null;
  standard_title: string;
  confidence: number;
  decision: string;
  notes: string | null;
  created_at: string | null;
}

export default function Home() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [recommendData, setRecommendData] = useState<RecommendResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [reviewConfirmations, setReviewConfirmations] = useState<Record<number, string>>({});

  // Citation checker
  const [citationInput, setCitationInput] = useState("");
  const [citationChecking, setCitationChecking] = useState(false);
  const [citationResult, setCitationResult] = useState<CitationResponse | null>(null);
  const [citationError, setCitationError] = useState<string | null>(null);

  // Reviews list
  const [reviewsList, setReviewsList] = useState<ReviewItem[]>([]);
  const [loadingReviews, setLoadingReviews] = useState(false);

  // Load stats on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/stats`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load stats");
        return res.json();
      })
      .then((data) => setStats(data))
      .catch((err) => console.error("Error loading stats:", err));

    loadReviews();
  }, []);

  const loadReviews = () => {
    setLoadingReviews(true);
    fetch(`${API_BASE}/api/reviews`)
      .then((res) => res.json())
      .then((data) => setReviewsList(data.reviews || []))
      .catch((err) => console.error("Error loading reviews:", err))
      .finally(() => setLoadingReviews(false));
  };

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchError(null);
    setRecommendData(null);
    setReviewConfirmations({});

    try {
      const res = await fetch(`${API_BASE}/api/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery.trim(), top_k: 5 }),
      });

      if (!res.ok) {
        throw new Error(`Search failed: ${res.statusText}`);
      }

      const data: RecommendResponse = await res.json();
      setRecommendData(data);
    } catch (err: any) {
      setSearchError("Backend not reachable. Make sure the FastAPI server is running on " + API_BASE);
    } finally {
      setSearching(false);
    }
  };

  const handleCitationCheck = async (citation: string) => {
    if (!citation.trim()) return;
    setCitationChecking(true);
    setCitationError(null);
    setCitationResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/check-citation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ citation: citation.trim() }),
      });

      if (!res.ok) {
        throw new Error(`Check failed: ${res.statusText}`);
      }

      const data: CitationResponse = await res.json();
      setCitationResult(data);
    } catch (err: any) {
      setCitationError("Failed to check citation. Please check connection.");
    } finally {
      setCitationChecking(false);
    }
  };

  const submitReview = async (standardId: number, decision: "accept" | "reject" | "flag", confidence: number) => {
    if (!recommendData) return;
    try {
      const res = await fetch(`${API_BASE}/api/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query_id: recommendData.query_id,
          standard_id: standardId,
          decision: decision,
          confidence: confidence,
          notes: `User marked as ${decision}`,
        }),
      });

      if (res.ok) {
        setReviewConfirmations((prev) => ({
          ...prev,
          [standardId]: `Marked as ${decision}!`,
        }));
        loadReviews();
      }
    } catch (err) {
      console.error("Failed to submit review:", err);
    }
  };

  const exampleQueries = [
    "cement for house foundation",
    "ordinary portland cement",
    "fly ash based cement",
    "TMT bars for building construction",
    "rebar tensile strength test",
  ];

  const exampleCitations = ["IS 1139:1966", "IS 1608:2005", "IS 269:2013", "IS 1489"];

  return (
    <div>
      <header>
        <div className="container header-content">
          <div>
            <h1>Standards Navigator</h1>
            <p className="tagline">
              Precision search, citation verification, and compliance navigator for Indian Standards (BIS).
            </p>
          </div>
          {stats && (
            <div className="stats-banner">
              {stats.total_standards} standards in database &bull; {stats.verified_count} verified
            </div>
          )}
        </div>
      </header>

      <main className="container">
        {/* Search Section */}
        <section className="search-section">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSearch(query);
            }}
            className="search-bar"
          >
            <input
              type="text"
              className="input-text"
              placeholder="Search by product, application, material, or IS number (e.g. 'cement for foundation')..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="submit" className="btn-primary" disabled={searching}>
              {searching ? "Searching..." : "Search Standards"}
            </button>
          </form>

          <div className="chips">
            <span className="chips-label">Try queries:</span>
            {exampleQueries.map((q) => (
              <button
                key={q}
                type="button"
                className="chip"
                onClick={() => {
                  setQuery(q);
                  handleSearch(q);
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </section>

        {/* Backend Error */}
        {searchError && (
          <div className="warning-card" style={{ background: "#fee2e2", borderColor: "#fca5a5", color: "#991b1b" }}>
            <strong>Error:</strong> {searchError}
          </div>
        )}

        {/* Search Warnings */}
        {recommendData && recommendData.warnings && recommendData.warnings.length > 0 && (
          <div className="warning-card">
            {recommendData.warnings.map((w, idx) => (
              <p key={idx}>&#9888; {w}</p>
            ))}
          </div>
        )}

        {/* Abstain State */}
        {recommendData && recommendData.abstain && (
          <div className="abstain-card">
            <div className="abstain-title">&#9432; No Direct Match Found</div>
            <p>{recommendData.message}</p>
          </div>
        )}

        {/* Results List */}
        {recommendData && !recommendData.abstain && (
          <div>
            <h2 style={{ fontSize: "1.1rem", marginBottom: "16px", color: "#475569" }}>
              Matching Standards ({recommendData.results.length})
            </h2>

            {recommendData.results.map((item) => {
              const partText = item.part ? ` Part ${item.part}` : "";
              const isCurrent = item.status.toLowerCase() === "current";
              const confPct = Math.round((item.confidence || 0) * 100);

              // Group allied standards by relation_type
              const alliedByType: Record<string, AlliedStandard[]> = {};
              (item.allied_standards || []).forEach((a) => {
                const rt = a.relation_type || "allied";
                if (!alliedByType[rt]) alliedByType[rt] = [];
                alliedByType[rt].push(a);
              });

              return (
                <div key={item.id} className="card">
                  <div className="card-header">
                    <div>
                      <span className="is-number">
                        {item.is_number}
                        {partText}
                      </span>
                    </div>
                    <div className="badges">
                      <span className="badge badge-group">{item.product_group}</span>
                      <span className={`badge ${isCurrent ? "badge-current" : "badge-superseded"}`}>
                        {item.status.toUpperCase()}
                      </span>
                      {item.latest_edition_year && (
                        <span className="badge badge-review">Ed. {item.latest_edition_year}</span>
                      )}
                      {item.amendment_count > 0 && (
                        <span className="badge badge-review">{item.amendment_count} Amend.</span>
                      )}
                      <span className="badge badge-review">
                        QCO: {item.certification?.status || "Needs review"}
                      </span>
                    </div>
                  </div>

                  <h3 className="card-title">{item.title}</h3>

                  {!isCurrent && item.superseded_by && (
                    <div
                      style={{
                        padding: "8px 12px",
                        background: "#fef2f2",
                        border: "1px solid #fecaca",
                        borderRadius: "4px",
                        marginBottom: "12px",
                        fontSize: "0.85rem",
                        color: "#991b1b",
                      }}
                    >
                      <strong>Superseded by:</strong> {item.superseded_by.is_number}
                      {item.superseded_by.part ? ` (Part ${item.superseded_by.part})` : ""} -{" "}
                      {item.superseded_by.title}
                    </div>
                  )}

                  <p className="scope-summary">
                    <strong>Scope:</strong> {item.scope_summary}
                  </p>

                  {item.why_it_applies && (
                    <p style={{ fontSize: "0.85rem", color: "#1e40af", marginBottom: "10px" }}>
                      <strong>Why it applies:</strong> {item.why_it_applies}
                    </p>
                  )}

                  {/* Confidence Bar */}
                  <div className="confidence-row">
                    <span>Relevance Match:</span>
                    <div className="progress-bar-bg">
                      <div className="progress-bar-fill" style={{ width: `${Math.max(confPct, 5)}%` }} />
                    </div>
                    <span>{confPct}%</span>
                  </div>

                  {/* Allied standards */}
                  {Object.keys(alliedByType).length > 0 && (
                    <div className="allied-section">
                      <div className="allied-title">Allied Standards &amp; Methods:</div>
                      {Object.entries(alliedByType).map(([relType, standards]) => (
                        <div key={relType} style={{ marginBottom: "4px" }}>
                          <span style={{ textTransform: "capitalize", fontWeight: 500, marginRight: "6px" }}>
                            {relType.replace("_", " ")}:
                          </span>
                          {standards.map((s, idx) => (
                            <span key={idx} className="allied-chip" title={s.title}>
                              {s.is_number}
                              {s.part ? ` P-${s.part}` : ""}
                            </span>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Card Footer Actions */}
                  <div className="card-footer">
                    <div>
                      {item.source_url ? (
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ fontSize: "0.85rem", color: "#2563eb", textDecoration: "none" }}
                        >
                          BIS Source Document &rarr;
                        </a>
                      ) : (
                        <span style={{ fontSize: "0.85rem", color: "#94a3b8" }}>No URL</span>
                      )}
                    </div>

                    <div className="actions">
                      {reviewConfirmations[item.id] ? (
                        <span style={{ fontSize: "0.8rem", color: "#166534", fontWeight: 600 }}>
                          &#10003; {reviewConfirmations[item.id]}
                        </span>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="btn-action btn-accept"
                            onClick={() => submitReview(item.id, "accept", item.confidence)}
                          >
                            Accept
                          </button>
                          <button
                            type="button"
                            className="btn-action btn-reject"
                            onClick={() => submitReview(item.id, "reject", item.confidence)}
                          >
                            Reject
                          </button>
                          <button
                            type="button"
                            className="btn-action btn-flag"
                            onClick={() => submitReview(item.id, "flag", item.confidence)}
                          >
                            Flag
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Check Citation Panel */}
        <section className="citation-panel">
          <h2 style={{ fontSize: "1.25rem", color: "#1e3a8a", marginBottom: "8px" }}>Check a Citation</h2>
          <p style={{ fontSize: "0.9rem", color: "#64748b", marginBottom: "16px" }}>
            Verify whether an Indian Standard citation is valid, current, outdated, or superseded.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleCitationCheck(citationInput);
            }}
            style={{ display: "flex", gap: "10px" }}
          >
            <input
              type="text"
              className="input-text"
              placeholder="e.g. 'IS 269:2015', 'IS 1139:1966', 'IS 1489'"
              value={citationInput}
              onChange={(e) => setCitationInput(e.target.value)}
            />
            <button type="submit" className="btn-primary" disabled={citationChecking}>
              {citationChecking ? "Checking..." : "Verify Citation"}
            </button>
          </form>

          <div className="chips">
            <span className="chips-label">Try citations:</span>
            {exampleCitations.map((c) => (
              <button
                key={c}
                type="button"
                className="chip"
                onClick={() => {
                  setCitationInput(c);
                  handleCitationCheck(c);
                }}
              >
                {c}
              </button>
            ))}
          </div>

          {citationError && (
            <div className="warning-card" style={{ marginTop: "16px" }}>
              {citationError}
            </div>
          )}

          {citationResult && (
            <div
              className={`citation-result ${
                citationResult.verdict === "ok"
                  ? "citation-ok"
                  : citationResult.verdict === "outdated_edition" || citationResult.verdict === "part_required"
                  ? "citation-amber"
                  : "citation-red"
              }`}
            >
              <div style={{ fontWeight: 700, marginBottom: "6px", textTransform: "uppercase" }}>
                Verdict: {citationResult.verdict.replace("_", " ")}
              </div>
              {citationResult.standard && (
                <div style={{ marginBottom: "6px" }}>
                  <strong>Standard:</strong> {citationResult.standard.title} (
                  {citationResult.standard.status})
                </div>
              )}
              {citationResult.messages.map((m, idx) => (
                <p key={idx} style={{ marginTop: "4px" }}>
                  &bull; {m}
                </p>
              ))}
            </div>
          )}
        </section>

        {/* Review Log Audit Section */}
        <section className="review-log-section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ fontSize: "1.25rem", color: "#1e3a8a" }}>Review &amp; Feedback Audit Log</h2>
            <button
              type="button"
              className="chip"
              onClick={loadReviews}
              disabled={loadingReviews}
            >
              {loadingReviews ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          <p style={{ fontSize: "0.85rem", color: "#64748b", marginTop: "4px" }}>
            Real-time log of human accept/reject/flag actions on query recommendations.
          </p>

          {reviewsList.length === 0 ? (
            <p style={{ marginTop: "14px", fontSize: "0.9rem", color: "#94a3b8" }}>No reviews logged yet.</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Query</th>
                    <th>Standard</th>
                    <th>Decision</th>
                    <th>Confidence</th>
                    <th>Notes</th>
                    <th>Logged At</th>
                  </tr>
                </thead>
                <tbody>
                  {reviewsList.map((rev) => (
                    <tr key={rev.id}>
                      <td>#{rev.id}</td>
                      <td>{rev.query_text}</td>
                      <td>
                        <strong>{rev.is_number}</strong>
                        {rev.part ? ` P-${rev.part}` : ""}
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            rev.decision === "accept"
                              ? "badge-current"
                              : rev.decision === "reject"
                              ? "badge-superseded"
                              : "badge-review"
                          }`}
                        >
                          {rev.decision.toUpperCase()}
                        </span>
                      </td>
                      <td>{Math.round(rev.confidence * 100)}%</td>
                      <td>{rev.notes || "-"}</td>
                      <td>{rev.created_at ? new Date(rev.created_at).toLocaleTimeString() : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
