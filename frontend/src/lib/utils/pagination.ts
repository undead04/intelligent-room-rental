export type PageItem = number | 'ellipsis-start' | 'ellipsis-end';

/**
 * Tạo danh sách trang hiển thị, vd: [1, '...', 4, 5, 6, '...', 20]
 * @param currentPage  trang hiện tại (bắt đầu từ 1)
 * @param totalPages   tổng số trang
 * @param siblingCount số trang hiển thị mỗi bên của trang hiện tại
 */
export function getPageRange(
  currentPage: number,
  totalPages: number,
  siblingCount = 1,
): PageItem[] {
  // 1 (đầu) + 1 (cuối) + 1 (hiện tại) + 2 siblings + 2 ellipsis
  const maxVisible = siblingCount * 2 + 5;

  if (totalPages <= maxVisible) {
    return range(1, totalPages);
  }

  const left = Math.max(currentPage - siblingCount, 1);
  const right = Math.min(currentPage + siblingCount, totalPages);

  const showStartEllipsis = left > 3;
  const showEndEllipsis = right < totalPages - 2;

  if (!showStartEllipsis && showEndEllipsis) {
    const leftCount = 3 + siblingCount * 2;
    return [...range(1, leftCount), 'ellipsis-end', totalPages];
  }

  if (showStartEllipsis && !showEndEllipsis) {
    const rightCount = 3 + siblingCount * 2;
    return [1, 'ellipsis-start', ...range(totalPages - rightCount + 1, totalPages)];
  }

  return [
    1,
    'ellipsis-start',
    ...range(left, right),
    'ellipsis-end',
    totalPages,
  ];
}

function range(start: number, end: number): number[] {
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}