CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE;

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
MERGE (n:Entity {id: row.id})
SET n.name = row.name,
    n.description = row.description,
    n.label = row.label
WITH n, row
CALL apoc.create.addLabels(n, [row.label]) YIELD node
RETURN count(node) AS nodes_loaded;

LOAD CSV WITH HEADERS FROM 'file:///edges.csv' AS row
MATCH (source:Entity {id: row.source})
MATCH (target:Entity {id: row.target})
CALL apoc.create.relationship(source, row.relationship, {}, target) YIELD rel
RETURN count(rel) AS relationships_loaded;
