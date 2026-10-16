-- Gas & Cost Splitter: shared PostgreSQL schema for Supabase.
-- Run this whole file once in the Supabase SQL Editor as the project owner.
-- It creates an isolated workspace with account-based access and Row Level
-- Security (RLS). Do not put a database password into the desktop app.

create extension if not exists pgcrypto;

create table if not exists public.gas_workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null check (char_length(trim(name)) between 1 and 100),
    created_at timestamptz not null default now()
);

create table if not exists public.gas_workspace_members (
    workspace_id uuid not null references public.gas_workspaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null default 'member' check (role in ('owner', 'member')),
    created_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create table if not exists public.gas_invites (
    code text primary key,
    workspace_id uuid not null references public.gas_workspaces(id) on delete cascade,
    created_by uuid not null references auth.users(id) on delete cascade,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null default now() + interval '7 days',
    used_at timestamptz,
    used_by uuid references auth.users(id) on delete set null
);

create table if not exists public.gas_settings (
    workspace_id uuid not null references public.gas_workspaces(id) on delete cascade,
    key text not null check (char_length(key) between 1 and 100),
    value text not null,
    primary key (workspace_id, key)
);

create table if not exists public.gas_trips (
    id bigint generated always as identity primary key,
    workspace_id uuid not null references public.gas_workspaces(id) on delete cascade,
    event_date date not null,
    driver text not null,
    kms numeric not null check (kms > 0),
    price_cents numeric check (price_cents is null or price_cents >= 0),
    fuel_efficiency numeric,
    attendees jsonb not null check (jsonb_typeof(attendees) = 'array'),
    notes text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.gas_expenses (
    id bigint generated always as identity primary key,
    workspace_id uuid not null references public.gas_workspaces(id) on delete cascade,
    event_date date not null,
    category text not null,
    description text not null,
    amount numeric not null check (amount > 0),
    payer text not null,
    attendees jsonb not null check (jsonb_typeof(attendees) = 'array'),
    notes text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.gas_payments (
    id bigint generated always as identity primary key,
    workspace_id uuid not null references public.gas_workspaces(id) on delete cascade,
    event_date date not null,
    payer text not null,
    payee text not null,
    amount numeric not null check (amount > 0),
    notes text not null default '',
    created_at timestamptz not null default now()
);

create table if not exists public.gas_expense_requests (
    id bigint generated always as identity primary key,
    workspace_id uuid not null references public.gas_workspaces(id) on delete cascade,
    request_token text not null,
    created_at timestamptz not null default now(),
    event_date date not null,
    category text not null,
    description text not null,
    amount numeric not null check (amount > 0),
    payer text not null,
    attendees jsonb not null check (jsonb_typeof(attendees) = 'array'),
    notes text not null default '',
    source text not null default '',
    unique (workspace_id, request_token)
);

create table if not exists public.gas_payment_requests (
    id bigint generated always as identity primary key,
    workspace_id uuid not null references public.gas_workspaces(id) on delete cascade,
    request_token text not null,
    created_at timestamptz not null default now(),
    event_date date not null,
    payer text not null,
    payee text not null,
    amount numeric not null check (amount > 0),
    notes text not null default '',
    source text not null default '',
    unique (workspace_id, request_token)
);

create index if not exists gas_trips_workspace_date on public.gas_trips(workspace_id, event_date desc);
create index if not exists gas_expenses_workspace_date on public.gas_expenses(workspace_id, event_date desc);
create index if not exists gas_payments_workspace_date on public.gas_payments(workspace_id, event_date desc);

-- SECURITY DEFINER helpers intentionally have a fixed search_path. RLS rules
-- call these to test the signed-in Supabase account's membership.
create or replace function public.gas_is_member(p_workspace_id uuid)
returns boolean
language sql stable security definer set search_path = public
as $$
    select exists (
        select 1 from public.gas_workspace_members
        where workspace_id = p_workspace_id and user_id = auth.uid()
    );
$$;

create or replace function public.gas_is_owner(p_workspace_id uuid)
returns boolean
language sql stable security definer set search_path = public
as $$
    select exists (
        select 1 from public.gas_workspace_members
        where workspace_id = p_workspace_id and user_id = auth.uid() and role = 'owner'
    );
$$;

create or replace function public.gas_create_workspace(p_name text)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
    new_workspace_id uuid;
begin
    if auth.uid() is null then
        raise exception 'You must be signed in.';
    end if;
    insert into public.gas_workspaces(name) values (trim(p_name)) returning id into new_workspace_id;
    insert into public.gas_workspace_members(workspace_id, user_id, role)
    values (new_workspace_id, auth.uid(), 'owner');
    return new_workspace_id;
end;
$$;

create or replace function public.gas_create_invite(p_workspace_id uuid)
returns text
language plpgsql security definer set search_path = public
as $$
declare
    target_workspace_id uuid;
    invite_code text;
begin
    target_workspace_id := p_workspace_id;
    if target_workspace_id is null or not public.gas_is_owner(target_workspace_id) then
        raise exception 'Only a workspace owner can create an invite.';
    end if;
    invite_code := encode(gen_random_bytes(18), 'hex');
    insert into public.gas_invites(code, workspace_id, created_by)
    values (invite_code, target_workspace_id, auth.uid());
    return invite_code;
end;
$$;

create or replace function public.gas_accept_invite(p_code text)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
    target_workspace_id uuid;
begin
    if auth.uid() is null then
        raise exception 'You must be signed in.';
    end if;
    select workspace_id into target_workspace_id
    from public.gas_invites
    where code = trim(p_code) and used_at is null and expires_at > now()
    for update;
    if target_workspace_id is null then
        raise exception 'That invite is invalid, expired, or already used.';
    end if;
    insert into public.gas_workspace_members(workspace_id, user_id, role)
    values (target_workspace_id, auth.uid(), 'member')
    on conflict (workspace_id, user_id) do nothing;
    update public.gas_invites set used_at = now(), used_by = auth.uid() where code = trim(p_code);
    return target_workspace_id;
end;
$$;

create or replace function public.gas_approve_expense_request(p_request_id bigint)
returns boolean
language plpgsql security definer set search_path = public
as $$
declare
    item public.gas_expense_requests%rowtype;
begin
    select * into item from public.gas_expense_requests where id = p_request_id for update;
    if not found or not public.gas_is_member(item.workspace_id) then
        return false;
    end if;
    insert into public.gas_expenses(workspace_id, event_date, category, description, amount, payer, attendees, notes)
    values (item.workspace_id, item.event_date, item.category, item.description, item.amount, item.payer, item.attendees, item.notes);
    delete from public.gas_expense_requests where id = item.id;
    return true;
end;
$$;

create or replace function public.gas_approve_payment_request(p_request_id bigint)
returns boolean
language plpgsql security definer set search_path = public
as $$
declare
    item public.gas_payment_requests%rowtype;
begin
    select * into item from public.gas_payment_requests where id = p_request_id for update;
    if not found or not public.gas_is_member(item.workspace_id) then
        return false;
    end if;
    insert into public.gas_payments(workspace_id, event_date, payer, payee, amount, notes)
    values (item.workspace_id, item.event_date, item.payer, item.payee, item.amount, item.notes);
    delete from public.gas_payment_requests where id = item.id;
    return true;
end;
$$;

-- The local-to-shared migration is intentionally a single database
-- transaction. It refuses a nonempty workspace and writes a marker, so a
-- network interruption cannot produce a half-imported or duplicated ledger.
create or replace function public.gas_import_legacy_snapshot(
    p_workspace_id uuid,
    p_snapshot jsonb,
    p_marker text
)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
    item jsonb;
begin
    if not public.gas_is_owner(p_workspace_id) then
        raise exception 'Only the workspace owner can migrate local data.';
    end if;
    if exists (
        select 1 from public.gas_settings
        where workspace_id = p_workspace_id and key = p_marker
    ) then
        raise exception 'This local database was already migrated.';
    end if;
    if exists (select 1 from public.gas_trips where workspace_id = p_workspace_id)
       or exists (select 1 from public.gas_expenses where workspace_id = p_workspace_id)
       or exists (select 1 from public.gas_payments where workspace_id = p_workspace_id) then
        raise exception 'The shared workspace must be empty before migration.';
    end if;

    insert into public.gas_settings(workspace_id, key, value)
    values
        (p_workspace_id, 'people', coalesce(p_snapshot->>'people', '[]')),
        (p_workspace_id, 'drivers', coalesce(p_snapshot->>'drivers', '{}'))
    on conflict (workspace_id, key) do update set value = excluded.value;

    for item in select value from jsonb_array_elements(coalesce(p_snapshot->'trips', '[]'::jsonb)) loop
        insert into public.gas_trips(workspace_id, event_date, driver, kms, price_cents, fuel_efficiency, attendees, notes)
        values (
            p_workspace_id, (item->>'event_date')::date, item->>'driver', (item->>'kms')::numeric,
            nullif(item->>'price_cents', '')::numeric, nullif(item->>'fuel_efficiency', '')::numeric,
            item->'attendees', coalesce(item->>'notes', '')
        );
    end loop;
    for item in select value from jsonb_array_elements(coalesce(p_snapshot->'expenses', '[]'::jsonb)) loop
        insert into public.gas_expenses(workspace_id, event_date, category, description, amount, payer, attendees, notes)
        values (
            p_workspace_id, (item->>'event_date')::date, item->>'category', item->>'description',
            (item->>'amount')::numeric, item->>'payer', item->'attendees', coalesce(item->>'notes', '')
        );
    end loop;
    for item in select value from jsonb_array_elements(coalesce(p_snapshot->'payments', '[]'::jsonb)) loop
        insert into public.gas_payments(workspace_id, event_date, payer, payee, amount, notes)
        values (
            p_workspace_id, (item->>'event_date')::date, item->>'payer', item->>'payee',
            (item->>'amount')::numeric, coalesce(item->>'notes', '')
        );
    end loop;
    for item in select value from jsonb_array_elements(coalesce(p_snapshot->'expense_requests', '[]'::jsonb)) loop
        insert into public.gas_expense_requests(workspace_id, request_token, event_date, category, description, amount, payer, attendees, notes, source)
        values (
            p_workspace_id, item->>'request_token', (item->>'event_date')::date, item->>'category',
            item->>'description', (item->>'amount')::numeric, item->>'payer', item->'attendees',
            coalesce(item->>'notes', ''), coalesce(item->>'source', '')
        );
    end loop;
    for item in select value from jsonb_array_elements(coalesce(p_snapshot->'payment_requests', '[]'::jsonb)) loop
        insert into public.gas_payment_requests(workspace_id, request_token, event_date, payer, payee, amount, notes, source)
        values (
            p_workspace_id, item->>'request_token', (item->>'event_date')::date, item->>'payer',
            item->>'payee', (item->>'amount')::numeric, coalesce(item->>'notes', ''), coalesce(item->>'source', '')
        );
    end loop;
    insert into public.gas_settings(workspace_id, key, value)
    values (p_workspace_id, p_marker, now()::text);
    return jsonb_build_object(
        'trips', jsonb_array_length(coalesce(p_snapshot->'trips', '[]'::jsonb)),
        'expenses', jsonb_array_length(coalesce(p_snapshot->'expenses', '[]'::jsonb)),
        'payments', jsonb_array_length(coalesce(p_snapshot->'payments', '[]'::jsonb))
    );
end;
$$;

revoke all on public.gas_workspaces, public.gas_workspace_members, public.gas_invites from anon, authenticated;
grant select, insert, update, delete on public.gas_settings, public.gas_trips, public.gas_expenses,
    public.gas_payments, public.gas_expense_requests, public.gas_payment_requests to authenticated;
grant usage, select on all sequences in schema public to authenticated;
revoke all on function public.gas_is_member(uuid), public.gas_is_owner(uuid), public.gas_create_workspace(text),
    public.gas_create_invite(uuid), public.gas_accept_invite(text), public.gas_approve_expense_request(bigint),
    public.gas_approve_payment_request(bigint), public.gas_import_legacy_snapshot(uuid, jsonb, text) from public;
grant execute on function public.gas_is_member(uuid), public.gas_is_owner(uuid), public.gas_create_workspace(text),
    public.gas_create_invite(uuid), public.gas_accept_invite(text), public.gas_approve_expense_request(bigint),
    public.gas_approve_payment_request(bigint) to authenticated;
grant execute on function public.gas_import_legacy_snapshot(uuid, jsonb, text) to authenticated;

alter table public.gas_settings enable row level security;
alter table public.gas_trips enable row level security;
alter table public.gas_expenses enable row level security;
alter table public.gas_payments enable row level security;
alter table public.gas_expense_requests enable row level security;
alter table public.gas_payment_requests enable row level security;

drop policy if exists gas_settings_member on public.gas_settings;
create policy gas_settings_member on public.gas_settings for all to authenticated
    using (public.gas_is_member(workspace_id)) with check (public.gas_is_member(workspace_id));
drop policy if exists gas_trips_member on public.gas_trips;
create policy gas_trips_member on public.gas_trips for all to authenticated
    using (public.gas_is_member(workspace_id)) with check (public.gas_is_member(workspace_id));
drop policy if exists gas_expenses_member on public.gas_expenses;
create policy gas_expenses_member on public.gas_expenses for all to authenticated
    using (public.gas_is_member(workspace_id)) with check (public.gas_is_member(workspace_id));
drop policy if exists gas_payments_member on public.gas_payments;
create policy gas_payments_member on public.gas_payments for all to authenticated
    using (public.gas_is_member(workspace_id)) with check (public.gas_is_member(workspace_id));
drop policy if exists gas_expense_requests_member on public.gas_expense_requests;
create policy gas_expense_requests_member on public.gas_expense_requests for all to authenticated
    using (public.gas_is_member(workspace_id)) with check (public.gas_is_member(workspace_id));
drop policy if exists gas_payment_requests_member on public.gas_payment_requests;
create policy gas_payment_requests_member on public.gas_payment_requests for all to authenticated
    using (public.gas_is_member(workspace_id)) with check (public.gas_is_member(workspace_id));

-- Ask PostgREST to reload its schema so the new tables/functions are usable.
notify pgrst, 'reload schema';
