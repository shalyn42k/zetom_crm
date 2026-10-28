// claude — "Pobierz z rejestru": company data by NIP from the MF VAT register
// (clients:nip_lookup -> crm/clients/services_nip_lookup.py). Used by the
// Alpine dialogs on the Klienci pages: call zetomNipLookup(this, url, opts)
// from a component that has `form` (name / nip / regon / address fields).
// opts.address: also fill street / post code / city / country (only the
// empty ones, so nothing typed is lost).
(function () {
  "use strict";
  window.zetomNipLookup = async function (component, url, opts) {
    opts = opts || {};
    var form = component.form;
    component.nipBusy = true;
    component.nipMsg = "";
    component.nipError = false;
    try {
      var r = await fetch(url + "?nip=" + encodeURIComponent(form.nip || ""), { headers: { "X-Requested-With": "fetch" } });
      var d = await r.json();
      if (!d.ok) {
        component.nipError = true;
        component.nipMsg = d.error;
        return;
      }
      form.nip = d.nip;
      form.name = d.name || form.name;
      if ("regon" in form) form.regon = d.regon || form.regon;
      if (opts.address) {
        ["street", "post_code", "city", "country"].forEach(function (k) {
          if (k in form && !form[k] && d[k]) form[k] = d[k];
        });
      }
      component.nipMsg = [d.name, d.address, d.status_vat ? "VAT: " + d.status_vat : ""].filter(Boolean).join(" · ");
    } catch (e) {
      component.nipError = true;
      component.nipMsg = opts.offline || "—";
    } finally {
      component.nipBusy = false;
    }
  };
})();
