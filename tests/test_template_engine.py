import unittest
from pathlib import Path

from project_brain.engines.template_engine import TemplateEngine
from project_brain.generators.prd_parser import PRDParser


class TemplateEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))
        self.engine = TemplateEngine()

    def test_viewmodel_context_has_required_keys(self) -> None:
        ctx = self.engine.viewmodel_context(self.brain, "HomeScreen")
        self.assertIn("package_name", ctx)
        self.assertIn("viewmodel_name", ctx)
        self.assertIn("ui_state_class", ctx)
        self.assertIn("dependencies", ctx)

    def test_render_viewmodel_produces_hilt_annotation(self) -> None:
        ctx = self.engine.viewmodel_context(self.brain, "HomeScreen")
        code = self.engine.render("viewmodel.kt.j2", ctx)
        self.assertIn("@HiltViewModel", code)
        self.assertIn("ViewModel()", code)
        self.assertIn("MutableStateFlow", code)
        self.assertIn("asStateFlow()", code)

    def test_render_viewmodel_has_private_mutable_stateflow(self) -> None:
        ctx = self.engine.viewmodel_context(self.brain, "HomeScreen")
        code = self.engine.render("viewmodel.kt.j2", ctx)
        self.assertIn("private val _uiState", code)
        self.assertIn("val uiState: StateFlow", code)

    def test_render_uistate_has_sealed_class_variants(self) -> None:
        ctx = self.engine.uistate_context(self.brain, "HomeScreen")
        code = self.engine.render("uistate.kt.j2", ctx)
        self.assertIn("sealed class", code)
        self.assertIn("data object Loading", code)
        self.assertIn("data class Success", code)
        self.assertIn("data class Error", code)

    def test_render_repository_interface_has_interface_keyword(self) -> None:
        ctx = self.engine.repository_interface_context(self.brain, "OrderRepository")
        code = self.engine.render("repository_interface.kt.j2", ctx)
        self.assertIn("interface", code)

    def test_render_repository_impl_has_firestore_injection(self) -> None:
        ctx = self.engine.repository_impl_context(self.brain, "OrderRepository")
        code = self.engine.render("repository_impl.kt.j2", ctx)
        self.assertIn("FirebaseFirestore", code)
        self.assertIn("@Inject constructor", code)

    def test_render_datamodel_has_keep_annotation(self) -> None:
        ctx = self.engine.datamodel_context(self.brain, "Order")
        code = self.engine.render("datamodel.kt.j2", ctx)
        self.assertIn("@Keep", code)
        self.assertIn("data class Order", code)

    def test_render_screen_scaffold_has_composable(self) -> None:
        ctx = self.engine.screen_scaffold_context(self.brain, "HomeScreen")
        code = self.engine.render("screen_scaffold.kt.j2", ctx)
        self.assertIn("@Composable", code)
        self.assertIn("hiltViewModel()", code)
        self.assertIn("collectAsState()", code)

    def test_render_nav_route_produces_object(self) -> None:
        ctx = self.engine.nav_route_context(self.brain, "HomeScreen")
        code = self.engine.render("nav_route.kt.j2", ctx)
        self.assertIn("object HomeRoute", code)
        self.assertIn("const val ROUTE", code)

    def test_render_nav_route_with_args_has_create_route(self) -> None:
        ctx = self.engine.nav_route_context(self.brain, "OrderTrackingScreen")
        code = self.engine.render("nav_route.kt.j2", ctx)
        self.assertIn("object OrderTrackingRoute", code)
        self.assertIn("createRoute", code)

    def test_render_di_module_has_binds_annotation(self) -> None:
        ctx = self.engine.di_module_context(self.brain, "order")
        code = self.engine.render("di_module.kt.j2", ctx)
        self.assertIn("@Module", code)
        self.assertIn("@Binds", code)

    def test_render_usecase_has_invoke_operator(self) -> None:
        ctx = self.engine.usecase_context(self.brain, "GetOrderUseCase")
        code = self.engine.render("usecase.kt.j2", ctx)
        self.assertIn("class GetOrderUseCase", code)
        self.assertIn("operator fun invoke", code)

    def test_render_viewmodel_test_has_test_dispatcher(self) -> None:
        ctx = self.engine.viewmodel_test_context(self.brain, "HomeScreen")
        code = self.engine.render("viewmodel_test.kt.j2", ctx)
        self.assertIn("StandardTestDispatcher", code)
        self.assertIn("@Before", code)
        self.assertIn("@After", code)

    def test_missing_screen_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.engine.viewmodel_context(self.brain, "NonExistentScreen")


if __name__ == "__main__":
    unittest.main()
