// Agent loop: orchestrates Gemini function calls until the model returns a final text answer
// or hits a step limit. Emits trace events so the caller can render reasoning live.

import { generate } from "./gemini.js";
import { TOOL_DECLARATIONS, TOOLS } from "./tools.js";

const SYSTEM_INSTRUCTION = `You are "Market Pulse", an agentic market analyst.

Your goal: generate a concise daily briefing for the user on gold, silver, and USD/INR, and deliver it via Telegram.

Your process, each time:
1. Call get_price for EACH of: gold, silver, usd_inr.
2. Call calc_change for EACH asset to compute day-over-day and 7-day moves.
3. Look at the changes. For any asset whose |day-over-day| is >= 0.5% OR |7-day| is >= 2%, call search_news with a focused query that might explain why. (e.g. gold moving: query "gold price fed inflation"; rupee weakening: "rupee depreciation RBI"). Skip news for assets that barely moved.
4. Write a short Markdown report (under 1500 chars) with:
   - One-line headline
   - Price table for all three assets with DoD%
   - "What moved and why" section that links significant moves to the news headlines (cite the source in parentheses).
   - A single closing sentiment line.
5. Call send_telegram with that report as the \`message\` argument. Use Markdown formatting.
6. After send_telegram returns ok, respond with a short plain-text confirmation to the user — do NOT call any more tools.

Rules:
- Always call get_price and calc_change for all three assets, even if some moves are tiny.
- Only call search_news when a move justifies it. Max 2 news searches per run.
- Never invent prices — only use values returned by tools.
- If a tool errors, mention it in the report and continue.`;

export async function runAgent({ apiKey, model, userPrompt, onStep, maxSteps = 12 }) {
  const contents = [{ role: "user", parts: [{ text: userPrompt }] }];
  const trace = [];

  const emit = (step) => {
    trace.push(step);
    if (onStep) onStep(step);
  };

  emit({ type: "user", text: userPrompt });

  for (let step = 0; step < maxSteps; step++) {
    let modelContent;
    try {
      modelContent = await generate({
        apiKey,
        model,
        contents,
        systemInstruction: SYSTEM_INSTRUCTION,
        tools: [{ functionDeclarations: TOOL_DECLARATIONS }],
        temperature: 0.4
      });
    } catch (err) {
      emit({ type: "error", text: `Gemini call failed: ${err.message}` });
      return { ok: false, trace, error: err.message };
    }

    contents.push(modelContent);

    const parts = modelContent.parts || [];
    const functionCalls = parts.filter((p) => p.functionCall).map((p) => p.functionCall);
    const textParts = parts.filter((p) => typeof p.text === "string" && p.text.trim());

    for (const t of textParts) {
      emit({ type: "thought", text: t.text.trim() });
    }

    if (!functionCalls.length) {
      const finalText = textParts.map((p) => p.text).join("\n").trim();
      emit({ type: "final", text: finalText || "(agent returned no text)" });
      return { ok: true, trace, final: finalText };
    }

    const functionResponses = [];
    for (const call of functionCalls) {
      const { name, args } = call;
      emit({ type: "tool_call", name, args });

      const impl = TOOLS[name];
      let result;
      try {
        if (!impl) throw new Error(`Unknown tool: ${name}`);
        result = await impl(args || {});
        emit({ type: "tool_result", name, result });
      } catch (err) {
        result = { error: err.message };
        emit({ type: "tool_error", name, error: err.message });
      }
      functionResponses.push({
        functionResponse: { name, response: result }
      });
    }

    contents.push({ role: "user", parts: functionResponses });
  }

  emit({ type: "error", text: `Hit max steps (${maxSteps}) without final answer.` });
  return { ok: false, trace, error: "max_steps_exceeded" };
}
