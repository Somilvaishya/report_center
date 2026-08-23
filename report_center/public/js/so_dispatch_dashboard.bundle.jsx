import React, { useState, useEffect, useCallback } from "react";
import ReactDOM from "react-dom/client";

/* ── Configurable thresholds ── */
const THRESHOLD_YELLOW = 3;
const THRESHOLD_RED = 5;

/* ── Colour palette ── */
const COLORS = {
  green:  { bg: "#ecfdf5", border: "#34d399", text: "#065f46", light: "#d1fae5", dot: "#10b981" },
  yellow: { bg: "#fffbeb", border: "#fbbf24", text: "#92400e", light: "#fef3c7", dot: "#f59e0b" },
  red:    { bg: "#fef2f2", border: "#f87171", text: "#991b1b", light: "#fee2e2", dot: "#ef4444" },
};

/* ── Pulse animation keyframes ── */
const pulseCSS = `
@keyframes so-pulse-ring {
  0%   { transform: scale(1);   opacity: 0.6; }
  100% { transform: scale(2.4); opacity: 0;   }
}
`;

/* ── Pulsing dot indicator ── */
const PulseDot = ({ color }) => (
  <span style={{ position:"relative", display:"inline-flex", width:12, height:12 }}>
    <span style={{
      position:"absolute", inset:0, borderRadius:"50%",
      backgroundColor: color,
      animation: "so-pulse-ring 1.4s ease-out infinite",
    }} />
    <span style={{
      position:"relative", width:12, height:12,
      borderRadius:"50%", backgroundColor: color,
    }} />
  </span>
);

/* ── KPI Card ── */
const Card = ({ title, count, type, active, onClick }) => {
  const c = COLORS[type];
  const isActive = active === type;
  return (
    <div onClick={() => onClick(type)} style={{
      position:"relative", padding:24, borderRadius:16,
      border: `2px solid ${isActive ? "#3b82f6" : c.border}`,
      backgroundColor: c.bg, cursor:"pointer",
      boxShadow: isActive
        ? "0 0 0 3px rgba(59,130,246,0.3)"
        : "0 1px 3px rgba(0,0,0,0.08)",
      transition: "all 0.2s ease",
      flex: "1 1 0%", minWidth: 200,
    }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
        <div>
          <p style={{
            fontSize:12, fontWeight:700, textTransform:"uppercase",
            letterSpacing:"0.05em", color: c.text, margin:0,
          }}>{title}</p>
          <h3 style={{ fontSize:36, fontWeight:700, color: c.text, margin:"8px 0 0" }}>
            {count}
          </h3>
        </div>
        {(type === "yellow" || type === "red") && count > 0 && (
          <PulseDot color={c.dot} />
        )}
      </div>
    </div>
  );
};

/* ── Main Dashboard ── */
const Dashboard = () => {
  const [data, setData] = useState({ counts: { green:0, yellow:0, red:0 }, orders: [] });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState(null);
  const [search, setSearch] = useState("");
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [sortCol, setSortCol] = useState("age");
  const [sortAsc, setSortAsc] = useState(false);

  const fetchData = useCallback(() => {
    setLoading(true);
    frappe.call({
      method: "report_center.report_center.page.so_dispatch_dashboar.so_dispatch_dashboar.get_so_dispatch_dashboard_data",
      callback: (r) => {
        if (r.message) {
          setData(r.message);
          setLastRefresh(new Date());
          const yc = r.message.counts.yellow;
          const rc = r.message.counts.red;
          if (rc > 0) {
            frappe.show_alert({
              message: rc + " order(s) critically delayed! " + yc + " delayed.",
              indicator: "red",
            }, 7);
          } else if (yc > 0) {
            frappe.show_alert({
              message: yc + " order(s) are delayed.",
              indicator: "orange",
            }, 5);
          }
        }
        setLoading(false);
      },
      error: () => setLoading(false),
    });
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [fetchData]);

  const handleCardClick = (type) => setFilter((prev) => (prev === type ? null : type));

  const handleSort = (col) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(true); }
  };

  const filtered = data.orders
    .filter((o) => !filter || o.delay_status === filter)
    .filter((o) => !search || (o.customer_name || "").toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      let va = a[sortCol], vb = b[sortCol];
      if (typeof va === "string") { va = va.toLowerCase(); vb = (vb || "").toLowerCase(); }
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });

  const fmtDate = (d) => (d ? new Date(d).toLocaleDateString() : "");

  const thStyle = {
    padding: "12px 16px", textAlign: "left", fontSize: 12, fontWeight: 600,
    textTransform: "uppercase", letterSpacing: "0.05em", color: "#64748b",
    borderBottom: "2px solid #e2e8f0", cursor: "pointer", userSelect: "none",
    background: "#f8fafc",
  };
  const tdStyle = { padding: "14px 16px", borderBottom: "1px solid #f1f5f9", fontSize: 14 };

  return (
    <div style={{
      fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
      background: "#f8fafc", padding: 24, minHeight: "80vh",
    }}>
      <style>{pulseCSS}</style>

      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "flex-end",
        marginBottom: 24, flexWrap: "wrap", gap: 12,
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#0f172a" }}>
            Sales Order Dispatch &amp; Delivery Tracker
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#94a3b8" }}>
            Real-time visibility into order fulfilment status
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontSize: 12, color: "#94a3b8" }}>
            Updated: {lastRefresh.toLocaleTimeString()}
          </span>
          <button
            onClick={fetchData}
            disabled={loading}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "8px 16px", background: "#fff",
              border: "1px solid #e2e8f0", borderRadius: 8,
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: 13, fontWeight: 500, color: "#334155",
              opacity: loading ? 0.5 : 1,
            }}
          >
            {loading ? "\u21BB Loading\u2026" : "\u21BB Refresh"}
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div style={{ display: "flex", gap: 20, marginBottom: 28, flexWrap: "wrap" }}>
        <Card
          title={"Under Time (< " + THRESHOLD_YELLOW + " Days)"}
          count={data.counts.green} type="green"
          active={filter} onClick={handleCardClick}
        />
        <Card
          title={"Delay (" + THRESHOLD_YELLOW + "\u2013" + THRESHOLD_RED + " Days)"}
          count={data.counts.yellow} type="yellow"
          active={filter} onClick={handleCardClick}
        />
        <Card
          title={"Too Delay (> " + THRESHOLD_RED + " Days)"}
          count={data.counts.red} type="red"
          active={filter} onClick={handleCardClick}
        />
      </div>

      {/* Data Table */}
      <div style={{
        background: "#fff", borderRadius: 16,
        border: "1px solid #e2e8f0", overflow: "hidden",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      }}>
        {/* Table header bar */}
        <div style={{
          padding: "16px 20px", display: "flex",
          justifyContent: "space-between", alignItems: "center",
          borderBottom: "1px solid #e2e8f0", flexWrap: "wrap", gap: 12,
        }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "#0f172a" }}>
            Open Sales Orders
            {filter && (
              <span style={{ fontSize: 12, fontWeight: 400, color: "#94a3b8", marginLeft: 8 }}>
                (filtered: {filter})
                {" "}
                <span
                  onClick={() => setFilter(null)}
                  style={{ color: "#3b82f6", cursor: "pointer", textDecoration: "underline" }}
                >clear</span>
              </span>
            )}
          </h2>
          <input
            type="text"
            placeholder="Search customer\u2026"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              padding: "8px 14px", border: "1px solid #e2e8f0",
              borderRadius: 8, width: 240, fontSize: 13, outline: "none",
            }}
          />
        </div>

        {/* Table */}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {[
                  ["order_no", "Order No."],
                  ["order_date", "Order Date"],
                  ["customer_name", "Customer"],
                  ["age", "Age (Days)"],
                  ["per_delivered", "% Delivered"],
                ].map(([k, label]) => (
                  <th key={k} onClick={() => handleSort(k)} style={thStyle}>
                    {label} {sortCol === k ? (sortAsc ? "\u2191" : "\u2193") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length > 0 ? (
                filtered.map((o) => {
                  const c = COLORS[o.delay_status] || COLORS.green;
                  return (
                    <tr
                      key={o.order_no}
                      style={{ borderLeft: "4px solid " + c.border, transition: "background 0.15s" }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = c.light; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                    >
                      <td style={{ ...tdStyle, fontFamily: "monospace", fontWeight: 600 }}>
                        <a
                          href={"/app/sales-order/" + o.order_no}
                          style={{ color: "#2563eb", textDecoration: "none" }}
                        >
                          {o.order_no}
                        </a>
                      </td>
                      <td style={tdStyle}>{fmtDate(o.order_date)}</td>
                      <td style={{ ...tdStyle, fontWeight: 500 }}>{o.customer_name}</td>
                      <td style={tdStyle}>
                        <span style={{
                          display: "inline-block", padding: "3px 10px",
                          borderRadius: 6, fontSize: 12, fontWeight: 700,
                          background: c.light, color: c.text,
                        }}>
                          {o.age} days
                        </span>
                      </td>
                      <td style={tdStyle}>{o.per_delivered}%</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} style={{ padding: 60, textAlign: "center", color: "#94a3b8" }}>
                    <div style={{ fontSize: 48, marginBottom: 8 }}>{"\uD83D\uDCE6"}</div>
                    <p style={{ fontSize: 16, fontWeight: 500, margin: 0 }}>No orders found</p>
                    <p style={{ fontSize: 13, margin: "4px 0 0" }}>
                      Try adjusting your filters or search.
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

/* ── Mount point ── */
window.renderDashboard = function(el) {
  var root = ReactDOM.createRoot(el);
  root.render(React.createElement(Dashboard));
};
