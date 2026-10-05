import './Pagination.css';

type PageItem = number | 'ellipsis-start' | 'ellipsis-end';

interface PaginationProps {
  /** Trang hiện tại (bắt đầu từ 1) */
  currentPage: number;
  /** Tổng số trang */
  totalPages: number;
  /** Gọi khi người dùng chọn trang khác */
  onPageChange: (page: number) => void;
  /** Số trang hiển thị mỗi bên trang hiện tại */
  siblingCount?: number;
  className?: string;
}

export function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  siblingCount = 1,
  className = '',
}: PaginationProps) {
  if (totalPages <= 1) return null;

  const items = getPageRange(currentPage, totalPages, siblingCount);
  const isFirst = currentPage === 1;
  const isLast = currentPage === totalPages;

  const goTo = (page: number) => {
    if (page < 1 || page > totalPages || page === currentPage) return;
    onPageChange(page);
  };

  return (
    <nav className={`pagination ${className}`} aria-label="Phân trang">
      <ul className="pagination__list">
        <li>
          <button
            type="button"
            className="pagination__btn"
            onClick={() => goTo(currentPage - 1)}
            disabled={isFirst}
            aria-label="Trang trước"
          >
            ‹
          </button>
        </li>

        {items.map((item) =>
          typeof item === 'number' ? (
            <li key={item}>
              <button
                type="button"
                className={`pagination__btn ${
                  item === currentPage ? 'pagination__btn--active' : ''
                }`}
                onClick={() => goTo(item)}
                aria-label={`Trang ${item}`}
                aria-current={item === currentPage ? 'page' : undefined}
              >
                {item}
              </button>
            </li>
          ) : (
            <li key={item} className="pagination__ellipsis" aria-hidden="true">
              …
            </li>
          ),
        )}

        <li>
          <button
            type="button"
            className="pagination__btn"
            onClick={() => goTo(currentPage + 1)}
            disabled={isLast}
            aria-label="Trang sau"
          >
            ›
          </button>
        </li>
      </ul>
    </nav>
  );
}

/**
 * Tạo danh sách trang hiển thị, vd: [1, '...', 4, 5, 6, '...', 20]
 * @param currentPage  trang hiện tại (bắt đầu từ 1)
 * @param totalPages   tổng số trang
 * @param siblingCount số trang hiển thị mỗi bên của trang hiện tại
 */
function getPageRange(currentPage: number, totalPages: number, siblingCount = 1): PageItem[] {
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