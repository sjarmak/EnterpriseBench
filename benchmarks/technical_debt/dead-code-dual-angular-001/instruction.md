# Find dead exported APIs in Angular framework that have no consumers outside Angular Components

The Angular team is preparing a major version release and wants to identify
public API exports from the Angular framework packages (@angular/core,
@angular/common, @angular/forms) that have zero external consumers — they are
only used within the Angular Components library (angular/components) and nowhere
else in the ecosystem.

These "effectively dead" exports are candidates for deprecation or removal. The
challenge is that some exports appear unused in the Angular framework repo itself
but are actually consumed by the Components library, making cross-repo analysis
essential.

Your task:

1. Identify public API exports from @angular/core, @angular/common, and
   @angular/forms that are exported in the public_api.ts files but have zero
   references within the Angular framework repo itself (excluding test files
   and the export declaration).
2. For each such "framework-orphan" export, search the Angular Components repo
   to determine if it is used there. Categorize each as:
   - "truly dead" — not used in either repo
   - "components-only" — used only in angular/components
   - "test-only" — used only in test files across both repos
3. For "components-only" exports, identify the specific Components packages
   that depend on them (e.g., @angular/material, @angular/cdk).
4. Document removal impact: if removed, which Components packages would break.

Write your analysis to /workspace/DEAD_CODE_REPORT.json with:
{
"dead_exports": [
{
"symbol": "<exported symbol name>",
"package": "<@angular/core|common|forms>",
"export_file": "<public_api.ts path in angular repo>",
"category": "<truly_dead|components_only|test_only>",
"components_usage": ["<paths in components repo>"],
"removal_impact": "<impact description>"
}
]
}
