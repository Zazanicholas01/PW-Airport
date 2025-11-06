CREATE USER metabase WITH PASSWORD 'metabase';
CREATE DATABASE metabase OWNER metabase;
GRANT ALL PRIVILEGES ON DATABASE metabase TO metabase;
