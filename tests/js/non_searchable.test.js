import { beforeEach, describe, expect, it, vi } from "vitest";
import {
	addFilter,
	addNonSearchableFilter,
	fireDomReady,
	installDjangoJQuery,
	resetJsEnvironment,
} from "./helpers.js";

const corePath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/core.js";
const nonSearchablePath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/non_searchable.js";

describe("non_searchable", () => {
	beforeEach(() => {
		vi.resetModules();
		resetJsEnvironment();
	});

	it("hides the search box when searchable is false", async () => {
		addNonSearchableFilter();
		const { select2 } = installDjangoJQuery();
		await import(nonSearchablePath);
		await import(corePath);
		await fireDomReady();

		expect(select2).toHaveBeenCalledWith({
			placeholder: "Search",
			width: "100%",
			minimumResultsForSearch: Number.POSITIVE_INFINITY,
		});
	});

	it("doesn't affect a searchable filter even when loaded", async () => {
		addFilter();
		const { select2 } = installDjangoJQuery();
		await import(nonSearchablePath);
		await import(corePath);
		await fireDomReady();

		expect(select2.mock.calls[0][0].minimumResultsForSearch).toBeUndefined();
	});
});
