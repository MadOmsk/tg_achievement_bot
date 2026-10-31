-- One database's schemas and what keeps the catalog shared (#234), run by
-- scripts/provision-postgres.sh as postgres. Safe to run again.
--
-- Each bot's own schema is its role's alone. The catalog belongs to a role both
-- are members of, so whichever bot migrates first, the other can still alter
-- what it made: an object made in `games` is handed to that role as it is made.

CREATE SCHEMA IF NOT EXISTS prod AUTHORIZATION unlocked_prod;
CREATE SCHEMA IF NOT EXISTS test AUTHORIZATION unlocked_test;
CREATE SCHEMA IF NOT EXISTS games AUTHORIZATION unlocked_games;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE :"database" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database" TO unlocked_prod, unlocked_test;
-- `CREATE SCHEMA IF NOT EXISTS`, which the bring-up says, asks this even when
-- the schema is there.
GRANT CREATE ON DATABASE :"database" TO unlocked_prod, unlocked_test;

CREATE OR REPLACE FUNCTION public.unlocked_games_owner() RETURNS event_trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    made record;
BEGIN
    FOR made IN
        SELECT object_type, object_identity FROM pg_event_trigger_ddl_commands()
        WHERE schema_name = 'games' AND command_tag LIKE 'CREATE %'
          AND object_type IN ('table', 'view', 'function')
    LOOP
        EXECUTE format('ALTER %s %s OWNER TO unlocked_games', made.object_type, made.object_identity);
    END LOOP;
END $$;

DROP EVENT TRIGGER IF EXISTS unlocked_games_owner;
CREATE EVENT TRIGGER unlocked_games_owner ON ddl_command_end
    EXECUTE FUNCTION public.unlocked_games_owner();
