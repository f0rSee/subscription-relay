import type { DeviceSettings } from "@/api/types"

const deviceProfiles = [
  { os: "iOS", model: "iPhone 15", versions: ["17.6.1", "18.3.2"] },
  { os: "iOS", model: "iPhone 15 Pro", versions: ["17.6.1", "18.3.2"] },
  { os: "iOS", model: "iPhone 16", versions: ["18.3.2", "18.5"] },
  { os: "iOS", model: "iPhone 16 Pro Max", versions: ["18.3.2", "18.5"] },
  { os: "Android", model: "Pixel 8", versions: ["14", "15"] },
  { os: "Android", model: "Pixel 9", versions: ["14", "15"] },
  { os: "Android", model: "SM-S921B", versions: ["14", "15"] },
  { os: "Android", model: "SM-S931B", versions: ["15"] },
] as const

function pick<T>(values: readonly T[]): T {
  return values[Math.floor(Math.random() * values.length)]
}

export function generateDeviceSettings(): DeviceSettings {
  const profile = pick(deviceProfiles)
  const clientId = Math.floor(Math.random() * 9_000_000_000_000) + 1_000_000_000_000

  return {
    user_agent: `VPNClient/2.0/${profile.os.toLowerCase()}/${clientId}`,
    hwid: crypto.randomUUID(),
    os: profile.os,
    os_version: pick<string>(profile.versions),
    model: profile.model,
  }
}
