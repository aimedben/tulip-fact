import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { ImportPage } from "./pages/ImportPage";
import { InvoiceReview } from "./pages/InvoiceReview";
import { HistoryPage } from "./pages/HistoryPage";
import { SuppliersPage } from "./pages/SuppliersPage";
import { ProductsPage } from "./pages/ProductsPage";
import { DatabasePage } from "./pages/DatabasePage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="invoices/:id" element={<InvoiceReview />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="suppliers" element={<SuppliersPage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="databases" element={<DatabasePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
