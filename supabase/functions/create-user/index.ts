// supabase/functions/create-user/index.ts
// Deploy: supabase functions deploy create-user
// Set secret: supabase secrets set SUPABASE_SERVICE_ROLE_KEY=...
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  try {
    const authHeader = req.headers.get('Authorization') ?? ''
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const anonKey = Deno.env.get('SUPABASE_ANON_KEY')!
    const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!

    // verify caller is admin using anon client + their JWT
    const userClient = createClient(supabaseUrl, anonKey, {
      global: { headers: { Authorization: authHeader } },
    })
    const { data: { user }, error: userErr } = await userClient.auth.getUser()
    if (userErr || !user) {
      return new Response(JSON.stringify({ error: 'Not authenticated' }), { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })
    }
    const { data: profile } = await userClient.from('profiles').select('role,status').eq('id', user.id).single()
    if (!profile || profile.role !== 'Administrator' || profile.status !== 'Active') {
      return new Response(JSON.stringify({ error: 'Admin only' }), { status: 403, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })
    }

    const body = await req.json()
    const { email, password, name, username, role, employee_id } = body
    if (!email || !password) {
      return new Response(JSON.stringify({ error: 'email and password required' }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })
    }

    const adminClient = createClient(supabaseUrl, serviceKey)
    const { data: created, error: createErr } = await adminClient.auth.admin.createUser({
      email,
      password,
      email_confirm: true,
      user_metadata: { name, username, role: role || 'Read-only staff', employee_id },
    })
    if (createErr) {
      return new Response(JSON.stringify({ error: createErr.message }), { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })
    }

    // ensure profile row
    await adminClient.from('profiles').upsert({
      id: created.user!.id,
      employee_id: employee_id || null,
      name: name || email,
      username: username || email.split('@')[0],
      role: role || 'Read-only staff',
      status: 'Active',
    })

    return new Response(JSON.stringify({ ok: true, user_id: created.user!.id }), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e) }), { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })
  }
})
