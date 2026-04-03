# Trace Django 5.0 model field changes that break Wagtail v5.2 dependent model assumptions

Your team maintains a Wagtail-based CMS running on Django. You're upgrading from
Django 4.2 to Django 5.0. Wagtail v5.2 claims Django 5.0 compatibility, but after
the upgrade, certain page models are failing migration checks and admin views are
raising FieldError exceptions.

The issue stems from Django 5.0's changes to model field internals and the
GeneratedField introduction, which affects how Wagtail's Page model hierarchy and
its StreamField implementation interact with Django's ORM.

Your task:
1. Identify the specific Django 5.0 model/field changes that affect ORM internals
   used by Wagtail — focus on changes to Field.contribute_to_class, model Meta
   handling, and the new GeneratedField.
2. Find all Wagtail model classes that inherit from or depend on Django model
   behavior that changed in 5.0 (Page, StreamField, Orderable, RevisionMixin).
3. Trace the impact chain: which Django internal changes break which specific
   Wagtail model operations (migrations, queries, admin serialization).
4. Identify the migration files in both repos that would need coordination.

Write your analysis to /workspace/SCHEMA_IMPACT.md with:
- Django 5.0 breaking changes relevant to Wagtail (with source file paths)
- Affected Wagtail models and their Django dependencies
- Impact chain showing which Django change breaks which Wagtail operation
- Migration coordination requirements
