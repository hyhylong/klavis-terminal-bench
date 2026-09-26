-- @common
CREATE TABLE app.inventory (
    sku text PRIMARY KEY,
    capacity bigint NOT NULL,
    available bigint NOT NULL
);
CREATE TABLE app.receipts (
    request_id text PRIMARY KEY,
    body jsonb NOT NULL,
    response jsonb NOT NULL
);

-- @source
CREATE TABLE app.orders (
    order_id text PRIMARY KEY,
    customer text NOT NULL,
    revision bigint NOT NULL,
    lines jsonb NOT NULL
);

-- @target
CREATE TABLE app.orders (
    order_id text PRIMARY KEY,
    customer text NOT NULL,
    revision bigint NOT NULL
);
CREATE TABLE app.order_lines (
    order_id text NOT NULL,
    position integer NOT NULL,
    sku text NOT NULL,
    quantity bigint NOT NULL,
    unit_price_cents bigint NOT NULL,
    PRIMARY KEY (order_id, position)
);
