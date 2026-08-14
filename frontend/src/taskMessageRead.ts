export function taskMessageReadStorageKey(
  role: string,
  displayName: string,
  stationId?: string | null,
): string {
  return `yitu-task-message-read:${role}:${displayName}:${stationId || 'unbound'}`
}

export function loadReadTaskMessageIds(key: string): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(key) || '[]')
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

export function saveReadTaskMessageIds(key: string, ids: string[]): void {
  localStorage.setItem(key, JSON.stringify([...new Set(ids)]))
}
