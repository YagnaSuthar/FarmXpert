'use client';

// ============================================================
// FILE: src/reusablefiles/datatable/DataTable.jsx
//
// Column-driven table. Replaces the hand-written <table> that the
// admin and super-admin pages each carried a near-identical copy of.
//
//   columns = [{ key, header, render?, align?, width?, className? }]
//   rows    = [ …any objects… ]
//
// `render(row, index)` returns the cell content, so a column can hold
// a pill, a select or a formatted date without this file knowing
// anything about the domain.
//
// Keeps the existing `.table-dash` / `.table-wrap-dash` classes, so the
// table's appearance is byte-for-byte what the dashboard already had.
// ============================================================

import React from 'react';

export default function DataTable({
  columns = [],
  rows = [],
  rowKey = (row, i) => row?.id ?? i,
  loading = false,
  loadingLabel,
  emptyLabel,
  onRowClick,
  caption,
  className = '',
}) {
  const colCount = columns.length || 1;

  return (
    <div className={`table-wrap-dash ${className}`.trim()}>
      <table className="table-dash">
        {caption ? <caption className="ui-table-caption">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width, textAlign: col.align }}
                className={col.className}
                scope="col"
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={colCount} className="ui-table-state">
                {loadingLabel}
              </td>
            </tr>
          ) : !rows.length ? (
            <tr>
              <td colSpan={colCount} className="ui-table-state is-empty">
                {emptyLabel}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr
                key={rowKey(row, i)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? 'is-clickable' : undefined}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    style={{ textAlign: col.align }}
                    className={col.className}
                  >
                    {col.render ? col.render(row, i) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
