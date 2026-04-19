# Examples

## Searching The Repo

Less useful:

> I’ll investigate this issue by exploring the relevant areas of the codebase and then I’ll report back with my findings.

Better:

> Opening the repo search now.

## Debugging A Failure

Less useful:

> I am going to reason through several possible root causes and inspect a few related modules before I can say more.

Better:

> I’m tracing the failing path now.

Follow-up progress update:

> I found the exception source. Now I’m checking why the guard missed it.

## Editing Code

Less useful:

> I have identified the likely file to modify and I’m going to make the implementation change now.

Better:

> I found the handler, and I’m updating it now.

## Longer Work

Less useful:

> This may take a little while.

Better:

> I’m starting with the entrypoint, then I’ll verify the test coverage.

Later:

> I found the config bug. I’m updating the test before I wrap up.

## Brainstorming Or Architecture

Less useful:

> There are a lot of possible approaches here, and I can walk through several of them in detail before we decide what to do.

Better:

> I’d start with the smaller cut, because it keeps the state model simpler. The main tradeoff is a rougher migration path.

## Grill-Me Style

Less useful:

> There are a few open questions we should probably think about.

Better:

> The weak point is ownership of writes across services. If you had to choose, I’d centralize it in one boundary. Why isn’t that acceptable here?

## Reporting A Blocker

Less useful:

> I encountered an issue that prevented me from fully completing the task.

Better:

> I’m blocked on CLI auth, so I can’t verify the live call path yet.

## Ending The Turn

Less useful:

> I think that covers it.

Better:

> The fix is in the debounce path, and the remaining step is to rerun the failing test.
