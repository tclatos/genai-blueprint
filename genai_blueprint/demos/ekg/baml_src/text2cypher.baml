// taken from https://kuzudb.github.io/blog/post/improving-text2cypher-for-graphrag-via-schema-pruning/


class Query {
  cypher string @description("Valid Cypher query with no newlines")
}

function Text2Cypher(question: string, schema: string) -> Query {
  client Gpt41mini
  prompt #"
    Translate the given question into a valid Cypher query that respects the given graph schema.

    <SYNTAX>
    - Relationship directions are VERY important to the success of a query. Here's an example: If
    the relationship `HAS_CREATOR` is marked as `from` A `to` B, it means that B created A.
    - Use short, concise alphanumeric strings as names of variable bindings (e.g., `a1`, `r1`, etc.)    
    - When comparing string properties, ALWAYS do the following:
      - Lowercase the property values before comparison
      - Use the WHERE clause
      - Use the CONTAINS operator to check for presence of one substring in the other
    - DO NOT use APOC as the database does not support it.
    - For datetime queries, use the TIMESTAMP type, which combines the date and time.
    </SYNTAX>

    <RETURN_RESULTS>
    - If the result is an integer, return it as an integer (not a string).
    - When returning results, return property values rather than the entire node or relationship.
    - Do not attempt to coerce data types to number formats (e.g., integer, float) in your results.
    - NO Cypher keywords should be returned by your query.
    </RETURN_RESULTS>

    {{ _.role("user") }}

    <QUESTION>
    {{ question }}
    </QUESTION>

    <SCHEMA>
    {{ schema }}
    </SCHEMA>

    <OUTPUT_FORMAT>
    {{ ctx.output_format }}
    </OUTPUT_FORMAT>
  "#
}