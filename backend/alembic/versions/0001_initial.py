"""Schemat początkowy Findini.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-07
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # unaccent() nie jest IMMUTABLE — opakowanie pozwala użyć go w indeksie.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
        """
    )

    op.execute(
        """
        CREATE TABLE guests (
            id uuid PRIMARY KEY,
            alias varchar(60) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            recovery_hash varchar(64) UNIQUE,
            recovery_created_at timestamptz,
            banned_at timestamptz,
            ban_reason varchar(300),
            deleted_at timestamptz
        );

        CREATE TABLE sessions (
            id uuid PRIMARY KEY,
            guest_id uuid NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            token_hash varchar(64) NOT NULL UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_used_at timestamptz NOT NULL DEFAULT now(),
            revoked_at timestamptz
        );
        CREATE INDEX ix_sessions_guest_id ON sessions(guest_id);

        CREATE TABLE reports (
            id uuid PRIMARY KEY,
            kind varchar(8) NOT NULL CHECK (kind IN ('lost', 'found')),
            status varchar(12) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'reserved', 'resolved', 'withdrawn', 'expired')),
            owner_id uuid NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            category varchar(32) NOT NULL,
            title varchar(80) NOT NULL,
            description text NOT NULL DEFAULT '',
            attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
            colors varchar(16)[] NOT NULL DEFAULT '{}',
            occurred_from timestamptz NOT NULL,
            occurred_to timestamptz NOT NULL,
            cell_id varchar(32) NOT NULL,
            public_lat double precision NOT NULL,
            public_lon double precision NOT NULL,
            public_geog geography(Point, 4326)
                GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(public_lon, public_lat), 4326)::geography) STORED,
            area_radius_m integer NOT NULL,
            area_label varchar(80),
            holding varchar(16) CHECK (holding IN ('with_finder', 'at_place', 'office')),
            holding_note varchar(120),
            search_text text NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            published_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            resolved_at timestamptz,
            withdrawn_at timestamptz,
            hidden_at timestamptz,
            hidden_reason varchar(300),
            CHECK (occurred_from <= occurred_to)
        );
        CREATE INDEX ix_reports_owner ON reports(owner_id);
        CREATE INDEX ix_reports_geog ON reports USING gist(public_geog);
        CREATE INDEX ix_reports_listing ON reports(kind, status, published_at DESC, id DESC);
        CREATE INDEX ix_reports_category ON reports(category, status);
        CREATE INDEX ix_reports_occurred ON reports(occurred_from, occurred_to);
        CREATE INDEX ix_reports_search_trgm ON reports USING gin (f_unaccent(lower(search_text)) gin_trgm_ops);
        CREATE INDEX ix_reports_colors ON reports USING gin(colors);

        CREATE TABLE report_private (
            report_id uuid PRIMARY KEY REFERENCES reports(id) ON DELETE CASCADE,
            exact_lat double precision NOT NULL,
            exact_lon double precision NOT NULL,
            accuracy_m integer,
            uncertainty_m integer NOT NULL DEFAULT 0,
            location_source varchar(8) NOT NULL CHECK (location_source IN ('gps', 'map')),
            secret_details text,
            claim_question varchar(200)
        );

        CREATE TABLE claims (
            id uuid PRIMARY KEY,
            report_id uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            claimant_id uuid NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            finder_id uuid NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            status varchar(12) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'rejected', 'withdrawn', 'returned', 'closed')),
            answer text NOT NULL,
            proof_details text NOT NULL DEFAULT '',
            lost_report_id uuid REFERENCES reports(id) ON DELETE SET NULL,
            finder_note varchar(300),
            handover_code varchar(8),
            handover_attempts smallint NOT NULL DEFAULT 0,
            finder_confirmed_at timestamptz,
            owner_confirmed_at timestamptz,
            accepted_at timestamptz,
            returned_at timestamptz,
            closed_at timestamptz,
            close_reason varchar(24),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (claimant_id <> finder_id),
            -- Jedna osoba = jedno roszczenie do danej rzeczy (także po odrzuceniu): utrudnia zgadywanie.
            CONSTRAINT uq_claim_once_per_person UNIQUE (report_id, claimant_id)
        );
        CREATE INDEX ix_claims_report ON claims(report_id);
        CREATE INDEX ix_claims_claimant ON claims(claimant_id);
        CREATE INDEX ix_claims_finder ON claims(finder_id);
        -- Najważniejsza gwarancja: co najwyżej jedno zaakceptowane/zwrócone roszczenie na przedmiot.
        CREATE UNIQUE INDEX uq_claims_single_release ON claims(report_id)
            WHERE status IN ('accepted', 'returned');

        CREATE TABLE photos (
            id uuid PRIMARY KEY,
            owner_id uuid NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            report_id uuid REFERENCES reports(id) ON DELETE SET NULL,
            claim_id uuid REFERENCES claims(id) ON DELETE SET NULL,
            purpose varchar(12) NOT NULL CHECK (purpose IN ('report', 'evidence')),
            storage_key varchar(80) NOT NULL,
            thumb_key varchar(80) NOT NULL,
            width integer NOT NULL,
            height integer NOT NULL,
            bytes integer NOT NULL,
            sha256 varchar(64) NOT NULL,
            position smallint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            embedding vector(512),
            embedding_model varchar(64),
            embedding_status varchar(10) NOT NULL DEFAULT 'pending'
                CHECK (embedding_status IN ('pending', 'ready', 'failed', 'skipped')),
            embedding_attempts smallint NOT NULL DEFAULT 0,
            embedding_error varchar(200),
            ai_suggestion jsonb,
            -- Dowody nigdy nie są indeksowane wektorowo.
            CHECK (purpose = 'report' OR embedding IS NULL)
        );
        CREATE INDEX ix_photos_owner ON photos(owner_id);
        CREATE INDEX ix_photos_report ON photos(report_id);
        CREATE INDEX ix_photos_claim ON photos(claim_id);
        CREATE INDEX ix_photos_pending ON photos(created_at) WHERE embedding_status = 'pending';

        CREATE TABLE messages (
            id bigserial PRIMARY KEY,
            claim_id uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            sender_id uuid REFERENCES guests(id) ON DELETE SET NULL,
            kind varchar(8) NOT NULL DEFAULT 'text' CHECK (kind IN ('text', 'system')),
            body text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_messages_claim ON messages(claim_id, id);

        CREATE TABLE claim_reads (
            claim_id uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            guest_id uuid NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            last_read_id bigint NOT NULL DEFAULT 0,
            PRIMARY KEY (claim_id, guest_id)
        );

        CREATE TABLE thanks (
            id uuid PRIMARY KEY,
            claim_id uuid NOT NULL UNIQUE REFERENCES claims(id) ON DELETE CASCADE,
            from_id uuid REFERENCES guests(id) ON DELETE SET NULL,
            to_id uuid REFERENCES guests(id) ON DELETE SET NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_thanks_to ON thanks(to_id);

        CREATE TABLE blocks (
            blocker_id uuid NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            blocked_id uuid NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (blocker_id, blocked_id)
        );

        CREATE TABLE abuse_reports (
            id uuid PRIMARY KEY,
            reporter_id uuid REFERENCES guests(id) ON DELETE SET NULL,
            target_type varchar(10) NOT NULL CHECK (target_type IN ('report', 'claim', 'message')),
            target_id varchar(40) NOT NULL,
            reason varchar(20) NOT NULL,
            details varchar(500) NOT NULL DEFAULT '',
            status varchar(10) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
            resolution_note varchar(300),
            created_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz,
            CONSTRAINT uq_abuse_once UNIQUE (reporter_id, target_type, target_id)
        );
        CREATE INDEX ix_abuse_status ON abuse_reports(status, created_at);
        CREATE INDEX ix_abuse_target ON abuse_reports(target_type, target_id);

        CREATE TABLE audit_events (
            id bigserial PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT now(),
            actor_id uuid,
            entity varchar(12) NOT NULL,
            entity_id uuid NOT NULL,
            action varchar(32) NOT NULL,
            from_status varchar(12),
            to_status varchar(12)
        );
        CREATE INDEX ix_audit_entity ON audit_events(entity_id);

        CREATE TABLE rate_buckets (
            key varchar(120) NOT NULL,
            window_start timestamptz NOT NULL,
            count integer NOT NULL DEFAULT 0,
            PRIMARY KEY (key, window_start)
        );
        CREATE INDEX ix_rate_buckets_window ON rate_buckets(window_start);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS rate_buckets, audit_events, abuse_reports, blocks, thanks, claim_reads, messages,
            photos, claims, report_private, reports, sessions, guests CASCADE;
        DROP FUNCTION IF EXISTS f_unaccent(text);
        """
    )
