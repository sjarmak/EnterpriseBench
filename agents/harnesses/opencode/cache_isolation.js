import { appendFile } from "node:fs/promises"

const telemetryPath = "/var/tmp/enterprisebench-cache-isolation.jsonl"

const cacheScope = () => {
  const scope = process.env.ENTERPRISEBENCH_CACHE_SCOPE
  if (!/^[a-f0-9]{32}$/.test(scope ?? "")) {
    throw new Error("ENTERPRISEBENCH_CACHE_SCOPE is missing or invalid")
  }
  return scope
}

const recordHook = async (hook, scope) => {
  const record = {
    type: "enterprisebench.cache_isolation_hook",
    scope,
    hook,
  }
  await appendFile(telemetryPath, `${JSON.stringify(record)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  })
}

export const EnterpriseBenchCacheIsolation = async () => ({
  "experimental.chat.system.transform": async (_input, output) => {
    const scope = cacheScope()
    const prefix = `EnterpriseBench cache isolation scope: ${scope}`
    output.system[0] = `${prefix}\n${output.system[0] ?? ""}`
    await recordHook("system", scope)
  },
  "chat.headers": async (_input, output) => {
    const scope = cacheScope()
    output.headers["X-Session-Id"] = scope
    output.headers["X-OpenRouter-Cache"] = "false"
    await recordHook("headers", scope)
  },
})
