#!/usr/bin/env python3
"""Rebuild unavailable exact-version libraries from pinned author sources.

Only packages native RPC resources; never loads or executes those binaries.
Requires Python 3.12+ and the JDK already required by the main project.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path.cwd()
REPO = ROOT / '.ci/legacy-maven'
SOURCES = [
    ('starscript', 'MeteorDevelopment/starscript', '033866258ffd6bf36f32611e865ecffdba0ddc46', '10bb59df3e86ca0afddbd94d286fb9d272459eb1534d640a5eb8a4873b5e97eb'),
    ('discord-rpc', 'MinnDevelopment/java-discord-rpc', 'c67048c4609f61e02fa6957a5eff601fcecd2fe2', 'bad784c20ea6a5823809d8a90039d1b2b5701b26f960867d3270c40cd5d24446'),
    ('discord-native', 'MinnDevelopment/discord-rpc-release', 'dc9dabe6aa41f6cfbf884d93086c4051fe0cbb95', 'b7258be63dc28fe8df76debdbbeb3fed0f00ac1bb541c269935201d0b0fdba48'),
]

def download(url, target):
    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '5', '--max-time', '120', url, '-o', str(target)], check=True)

def maven(group, artifact, version, files, dependencies=''):
    destination = REPO / group.replace('.', '/') / artifact / version
    destination.mkdir(parents=True, exist_ok=True)
    jar = destination / f'{artifact}-{version}.jar'
    with zipfile.ZipFile(jar, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, name in files:
            z.write(path, name)
    (destination / f'{artifact}-{version}.pom').write_text(
        f'<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version><dependencies>{dependencies}</dependencies></project>')
    return jar

def dependency(group, name, version):
    return f'<dependency><groupId>{group}</groupId><artifactId>{name}</artifactId><version>{version}</version></dependency>'

properties = dict(line.split('=', 1) for line in (ROOT / 'gradle.properties').read_text().splitlines() if '=' in line and not line.lstrip().startswith('#'))
assert properties['starscript_version'] == '0.1.5', 'Update source pins for the requested Starscript version'
assert properties['discordrpc_version'] == '2.0.2', 'Update source pins for the requested RPC version'
if REPO.exists():
    shutil.rmtree(REPO)
REPO.mkdir(parents=True)
evidence = []
with tempfile.TemporaryDirectory(prefix='meteor-legacy-', dir=os.environ.get('RUNNER_TEMP')) as directory:
    temp = Path(directory)
    source_roots = {}
    for name, author, commit, expected in SOURCES:
        archive = temp / (name + '.tar.gz')
        url = f'https://codeload.github.com/{author}/tar.gz/{commit}'
        download(url, archive)
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        assert actual == expected, f'Author source archive changed: {name}'
        destination = temp / name
        destination.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(destination, filter='data')
        source_roots[name] = next(destination.iterdir())
        evidence.append({'name': name, 'author_url': url, 'commit': commit, 'archive_sha256': actual})
    jars = []
    for group, artifact, version in [('net.java.dev.jna', 'jna', '4.4.0'), ('com.google.code.findbugs', 'jsr305', '3.0.2')]:
        url = f'https://repo.maven.apache.org/maven2/{group.replace(".", "/")}/{artifact}/{version}/{artifact}-{version}.jar'
        jar = temp / f'{artifact}.jar'
        download(url, jar)
        digest = temp / f'{artifact}.sha1'
        download(url + '.sha1', digest)
        assert hashlib.sha1(jar.read_bytes()).hexdigest() == digest.read_text().split()[0].strip(), f'Maven checksum mismatch: {artifact}'
        jars.append(jar)
    java_bin = Path(os.environ['JAVA_HOME']) / 'bin'
    for name, group, artifact, version, dependencies in [
        ('starscript', 'meteordevelopment', 'starscript', '0.1.5', ''),
        ('discord-rpc', 'club.minnced', 'java-discord-rpc', '2.0.2', dependency('net.java.dev.jna', 'jna', '4.4.0') + dependency('club.minnced', 'discord-rpc-release', 'v3.4.0')),
    ]:
        source = source_roots[name]
        classes = temp / (name + '-classes')
        classes.mkdir()
        inputs = sorted((source / 'src/main/java').rglob('*.java'))
        assert inputs
        subprocess.run([str(java_bin / 'javac'), '--release', '8', '-encoding', 'UTF-8', '-classpath', os.pathsep.join(map(str, jars)), '-d', str(classes)] + list(map(str, inputs)), check=True)
        files = [(p, p.relative_to(classes).as_posix()) for p in classes.rglob('*') if p.is_file()]
        files.append((source / 'LICENSE', 'META-INF/LICENSE'))
        output = maven(group, artifact, version, files, dependencies)
        evidence.append({'artifact': output.relative_to(ROOT).as_posix(), 'classes': len(files) - 1, 'jar_sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
    resources = source_roots['discord-native'] / 'src/main/resources'
    files = [(p, p.relative_to(resources).as_posix()) for p in resources.rglob('*') if p.is_file()]
    assert len(files) == 4, 'Expected four author-provided platform resources'
    maven('club.minnced', 'discord-rpc-release', 'v3.4.0', files)
(REPO / 'provenance.json').write_text(json.dumps(evidence, indent=2) + '\n')
print('Restored exact legacy dependencies; native resources were packaged only.')
