Run `python3 .ci/restore-legacy-deps.py` with Python 3.12+ and JAVA_HOME pointing to JDK 17 before `./gradlew build`.

The helper rebuilds Starscript 0.1.5 and Java Discord RPC 2.0.2 from fixed author commits because the original binary repositories no longer serve these versions. It creates a scoped local Maven repository without modifying application APIs or changing library versions. Native RPC v3.4.0 resources are copied from the exact author tag and packaged without execution. JNA 4.4.0 and compile-only annotations 3.0.2 are checksum-checked against Maven Central. Generated source/archive and JAR hashes are retained in `.ci/legacy-maven/provenance.json`.

The Mac mini CI invokes this helper automatically before the original Gradle build and uploads the provenance alongside build artifacts. Rebuilding dependencies does not itself prove application compilation or native runtime compatibility; the full original Gradle build remains required.
