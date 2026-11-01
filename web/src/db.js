import { supabase } from './supabaseClient'

/**
 * Insert a row, and if the remote table still declares a staff column as uuid
 * (left over from the original Supabase Auth schema) retry with that column
 * set to null instead of failing the action.
 */
export async function insertTolerant(table, row, uuidFields = []) {
  const first = await supabase.from(table).insert(row)
  if (first.error && /uuid/i.test(first.error.message) && uuidFields.length) {
    const retry = { ...row }
    uuidFields.forEach(f => { retry[f] = null })
    const second = await supabase.from(table).insert(retry)
    return { ...second, degraded: !second.error }
  }
  return first
}
