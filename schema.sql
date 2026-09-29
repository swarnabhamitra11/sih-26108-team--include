CREATE OR REPLACE FUNCTION immutable_array_to_string(arr text[]) RETURNS text LANGUAGE sql IMMUTABLE AS $$ SELECT array_to_string($1, ' '); $$;

-- standards schema
CREATE EXTENSION IF NOT EXISTS vector; -- pgvector

-- Lookup tables
CREATE TABLE product_group (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

INSERT INTO product_group (name) VALUES
    ('Cement'),
    ('Steel'),
    ('Cables'),
    ('Pipes'),
    ('Pumps');

CREATE TABLE family (
    id               SERIAL PRIMARY KEY,
    base_is_number   TEXT NOT NULL UNIQUE   -- e.g. "IS 1489" (base designation without part/year)
);

-- Core standards table
CREATE TABLE standards (
    id               SERIAL PRIMARY KEY,
    is_number        TEXT NOT NULL,                     -- base IS designation (no part or year)
    title            TEXT NOT NULL,
    part             TEXT,
    family_id        INTEGER NOT NULL REFERENCES family(id),
    product_group    INTEGER REFERENCES product_group(id),
    embedding        vector(%%EMBEDDING_DIM%%),
    verification_status TEXT NOT NULL CHECK (verification_status IN ('entered','reviewed','verified')) DEFAULT 'entered',
    scope_text       TEXT NOT NULL,
    keywords         TEXT[],
    status           TEXT CHECK (status IN ('current','superseded','withdrawn')) DEFAULT 'current',
    superseded_by_id INTEGER REFERENCES standards(id),
    source_url       TEXT,
    source_note      TEXT,
    category         TEXT,
    tsv              tsvector GENERATED ALWAYS AS (
                        to_tsvector('english',
                                    coalesce(title,'') || ' ' ||
                                    coalesce(scope_text,'') || ' ' ||
                                    immutable_array_to_string(coalesce(keywords, '{}'::text[]))
                                   )
                      ) STORED,
    UNIQUE NULLS NOT DISTINCT (is_number, part),
    CHECK (superseded_by_id IS NULL OR status = 'superseded')
);
CREATE INDEX idx_standards_tsv ON standards USING GIN (tsv);

-- Certification rules
CREATE TYPE cert_status AS ENUM ('mandatory','voluntary','needs_review');

CREATE TABLE certification_rules (
    id               SERIAL PRIMARY KEY,
    standard_id      INTEGER NOT NULL REFERENCES standards(id),
    status           cert_status NOT NULL,
    order_reference  TEXT,
    source_note      TEXT,
    verified         BOOLEAN NOT NULL DEFAULT FALSE,
    product_scope_text TEXT,
    scope_keywords    TEXT[],
    CHECK (status <> 'mandatory' OR (source_note IS NOT NULL AND source_note <> ''))
);

-- Benchmark rows
CREATE TABLE benchmark_rows (
    id               SERIAL PRIMARY KEY,
    query            TEXT NOT NULL UNIQUE,
    language         TEXT,
    kind             TEXT NOT NULL CHECK (kind IN ('normal','abstain')) DEFAULT 'normal',
    verification_status TEXT NOT NULL CHECK (verification_status IN ('entered','reviewed','verified')) DEFAULT 'entered'
);

-- Expected standards for each benchmark row
CREATE TABLE benchmark_expected (
    id               SERIAL PRIMARY KEY,
    benchmark_row_id INTEGER NOT NULL REFERENCES benchmark_rows(id) ON DELETE CASCADE,
    standard_id      INTEGER NOT NULL REFERENCES standards(id),
    role             TEXT NOT NULL CHECK (role IN ('primary','allied'))
);

-- Queries (live query records)
CREATE TABLE queries (
    id                SERIAL PRIMARY KEY,
    query_text        TEXT NOT NULL,
    language          TEXT,
    extracted_attributes JSONB,
    result_ids        INTEGER[],
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reviews (decisions on live query results)
CREATE TABLE reviews (
    id                SERIAL PRIMARY KEY,
    query_id          INTEGER NOT NULL REFERENCES queries(id),
    selected_standard_id INTEGER NOT NULL REFERENCES standards(id),
    confidence        REAL NOT NULL,
    decision          TEXT NOT NULL CHECK (decision IN ('accept','reject','flag')),
    notes             TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Standard editions (year revisions)
CREATE TABLE standard_editions (
    id           SERIAL PRIMARY KEY,
    standard_id  INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    edition_year INTEGER NOT NULL,
    is_latest    BOOLEAN NOT NULL DEFAULT FALSE,
    notes        TEXT
);
CREATE UNIQUE INDEX uq_standard_editions ON standard_editions (standard_id, edition_year);
CREATE UNIQUE INDEX uq_standard_editions_latest ON standard_editions (standard_id) WHERE is_latest;

-- Standard amendments (per edition)
CREATE TABLE standard_amendments (
    id           SERIAL PRIMARY KEY,
    edition_id   INTEGER NOT NULL REFERENCES standard_editions(id) ON DELETE CASCADE,
    amendment_no INTEGER NOT NULL,
    year         INTEGER,
    notes        TEXT
);
CREATE UNIQUE INDEX uq_standard_amendments ON standard_amendments (edition_id, amendment_no);

-- Standard relations (graph edges)
CREATE TABLE standard_relations (
    id                 SERIAL PRIMARY KEY,
    from_standard_id   INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    to_standard_id     INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    relation_type      TEXT CHECK (relation_type IN ('normative_ref','test_method','terminology','safety','installation','product')),
    notes              TEXT
);
CREATE UNIQUE INDEX uq_standard_relations ON standard_relations (from_standard_id, to_standard_id, relation_type);

-- Unique constraint for benchmark_expected
CREATE UNIQUE INDEX uq_benchmark_expected ON benchmark_expected (benchmark_row_id, standard_id);

-- Note: %%EMBEDDING_DIM%% is substituted from the .env file by the Python init script before execution.
