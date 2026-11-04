/* One saved snapshot per page load. No timers, model requests or polling. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const percent = value => `${Number(value.toFixed(1))}%`;
  const money = value => value.toLocaleString("en-US", { style: "currency", currency: "USD" });
  const signed = value => `${value < 0 ? "−" : "+"}${Number(Math.abs(value).toFixed(1))} pp`;
  const timestamp = value => {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return null;
    return new Intl.DateTimeFormat("en", {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      timeZone: "UTC", timeZoneName: "short"
    }).format(date);
  };

  async function loadSnapshot() {
    try {
      const response = await fetch("overview.json", { cache: "no-store" });
      if (!response.ok) throw new Error("Snapshot unavailable");
      const data = await response.json();
      const comparison = data.comparison;
      const models = comparison?.models;
      const usage = data.observed_usage_usd;
      if (data.schema_version !== 1 || comparison?.count !== 200 || comparison.mode !== "nonthinking"
          || comparison.max_output_tokens !== 512 || comparison.official_test !== false
          || !Array.isArray(models) || models.length !== 4
          || !usage || ![usage.modal, usage.deepseek].every(value => Number.isFinite(value) && value >= 0)) {
        throw new Error("Unexpected snapshot");
      }
      for (const model of models) {
        if (!Number.isInteger(model.correct) || model.correct < 0 || model.correct > 200
            || !Number.isFinite(model.percent) || model.percent < 0 || model.percent > 100
            || Math.abs(model.percent - model.correct / 2) > 0.000001
            || !Number.isFinite(model.delta_vs_granite_base_pp)
            || Math.abs(model.delta_vs_granite_base_pp - (model.percent - models[1].percent)) > 0.000001) {
          throw new Error("Invalid matched comparison");
        }
      }
      models.forEach((model, index) => {
        byId(`bar-${index}`).style.width = `${model.percent}%`;
        byId(`percent-${index}`).textContent = percent(model.percent);
        byId(`correct-${index}`).textContent = `${model.correct} / 200`;
        byId(`accuracy-${index}`).textContent = percent(model.percent);
        byId(`delta-${index}`).textContent = index === 1 ? "Reference"
          : (index === 0 ? "Teacher gap " : "") + signed(model.delta_vs_granite_base_pp);
      });
      byId("comparison-chart").setAttribute("aria-label",
        `Accuracy on 200 matched development questions: DeepSeek ${models[0].percent} percent, original Granite ${models[1].percent} percent, random-data trained Granite ${models[2].percent} percent, skill-ranked Granite ${models[3].percent} percent.`);
      byId("teacher-gap").textContent = String(Number(models[0].delta_vs_granite_base_pp.toFixed(1)));
      byId("modal-usage").textContent = money(usage.modal);
      byId("deepseek-usage").textContent = money(usage.deepseek);
      if (typeof data.latest_attempt === "string" && data.latest_attempt.length <= 1800) {
        byId("latest-attempt").textContent = data.latest_attempt;
      }
      if (typeof data.billing_note === "string" && data.billing_note.length <= 1800) {
        byId("billing-note").textContent = data.billing_note;
      }
      const asOf = timestamp(data.usage_as_of_utc);
      if (asOf) byId("usage-as-of").textContent = `Snapshot: ${asOf}.`;
      const updated = timestamp(data.updated_at_utc);
      if (data.project_status === "stopped_at_user_request" && data.stop_verified === true
          && data.active_gpu_tasks === 0 && data.paid_work_enabled === false) {
        byId("snapshot-note").textContent = `Stopped status verified${updated ? ` · ${updated}` : ""}. This page loads one saved snapshot and does not poll.`;
      }
    } catch {
      byId("snapshot-note").textContent = "Showing the saved results summary. Snapshot metadata could not be loaded; this page does not poll.";
    }
  }
  loadSnapshot();
})();
