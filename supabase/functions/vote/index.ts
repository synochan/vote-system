import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

type VotePayload = {
  user_id: string;
  poll_id: string;
  choice: string;
  edge_node_id: string;
  created_at: string;
};

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function isValidVote(payload: Partial<VotePayload>): payload is VotePayload {
  return Boolean(
    payload.user_id &&
      payload.poll_id &&
      payload.choice &&
      payload.edge_node_id &&
      payload.created_at,
  );
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (request.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "Method not allowed" }),
      {
        status: 405,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

  if (!supabaseUrl || !serviceRoleKey) {
    return new Response(
      JSON.stringify({ error: "Missing Supabase environment variables" }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  let payload: Partial<VotePayload>;

  try {
    payload = await request.json();
  } catch {
    return new Response(
      JSON.stringify({ error: "Invalid JSON body" }),
      {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  if (!isValidVote(payload)) {
    return new Response(
      JSON.stringify({
        error: "Missing required fields",
        required_fields: [
          "user_id",
          "poll_id",
          "choice",
          "edge_node_id",
          "created_at",
        ],
      }),
      {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  const createdAt = new Date(payload.created_at);
  if (Number.isNaN(createdAt.getTime())) {
    return new Response(
      JSON.stringify({ error: "created_at must be a valid ISO timestamp" }),
      {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  const supabase = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false },
  });

  const { data, error } = await supabase
    .from("raw_votes")
    .insert({
      user_id: payload.user_id,
      poll_id: payload.poll_id,
      choice: payload.choice,
      edge_node_id: payload.edge_node_id,
      created_at: payload.created_at,
    })
    .select("id, received_at, status")
    .single();

  if (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  return new Response(
    JSON.stringify({
      status: "accepted",
      vote_id: data.id,
      queue_status: data.status,
      received_at: data.received_at,
    }),
    {
      status: 202,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    },
  );
});
