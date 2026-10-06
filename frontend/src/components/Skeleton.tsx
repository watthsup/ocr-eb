export function Block({ w = '100%', h = 14, r }: { w?: string | number; h?: number; r?: number }) {
  return <div className="skeleton" style={{ width: w, height: h, borderRadius: r }} />;
}

/** Placeholder for the results dashboard while a job is processing. */
export default function DashboardSkeleton() {
  return (
    <div className="ui-card fade-in" aria-busy="true" aria-label="Loading results">
      <div className="card-body">
        <div className="skeleton-stack">
          <div className="skeleton-row" style={{ justifyContent: 'space-between' }}>
            <Block w={260} h={26} />
            <Block w={220} h={36} r={10} />
          </div>
          <Block w={360} h={12} />
          <div className="skeleton-row">
            {[0, 1, 2, 3, 4].map((i) => <Block key={i} h={58} r={10} />)}
          </div>
          <Block w={340} h={36} r={10} />
          {[0, 1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="skeleton-row">
              <Block w="30%" h={30} />
              <Block w="15%" h={30} />
              <Block w="25%" h={30} />
              <Block w="15%" h={30} />
              <Block w="15%" h={30} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
