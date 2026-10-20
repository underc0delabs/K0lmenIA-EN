---
name: blockchain-testing
description: How to test blockchain / Web3 applications and smart contracts — networks and environments (mainnet vs. Sepolia/Holesky testnets, Hardhat/Anvil/Ganache local nodes, mainnet forking), smart contracts in Solidity/EVM (and notions of other chains), functionality (view/pure functions vs. state-changing ones, events/logs, return values, require/revert and custom errors), tokens and standards (ERC-20, ERC-721, ERC-1155, allowance/approve, decimals), gas (estimation, out-of-gas, limits), smart contract security (reentrancy, overflow/underflow, access control and onlyOwner, front-running/MEV, manipulable oracles, delegatecall, randomness, DoS, proxy initialization), upgradeability (UUPS/Transparent proxies, storage layout), signatures and permits (EIP-712, permit, replay), dApp↔contract integration (wallet/MetaMask, handling of reverts and confirmations, reorg, nonce, chain id), testing with Hardhat/Foundry (unit, fuzzing, invariants), static analysis (Slither, Mythril) and coverage, gas reporting, and testnets with faucets; typical bugs and questions for the team. Used by the blockchain-tester.
---

# Blockchain / Web3 and smart contract testing

A smart contract is **immutable once deployed** and handles **real value**: a bug cannot be "patched" like in a normal app and can cost funds. That is why it is tested to a high standard, on **testnets or local nodes**, never with real funds on mainnet for QA. Deep security work is coordinated with `security-analyst` / an auditor.

## 1. Networks and environments

- **Never mainnet with real funds** for QA. Use a **testnet** (Sepolia, Holesky) with faucets, or a **local node** (Hardhat Network, Foundry/Anvil, Ganache).
- **Mainnet forking**: run a local copy of the real state to test integrations (with already deployed protocols) without spending.
- Confirm the **chain** (Ethereum/EVM, an L2 like Arbitrum/Optimism/Polygon, or another one like Solana) and the **chain id**.

## 2. Contract functionality

- **view/pure** (they read; calling them off-chain costs no gas) vs. those that **change state** (transactions, cost gas, emit events).
- **Events/logs**: every important action emits the right event with the right parameters (the dApp and the indexers depend on them).
- **require/revert and custom errors**: preconditions are validated and revert with the right reason; test that an invalid operation **reverts** (not that it fails silently or leaves a half-done state).
- Consistent **return values** and state changes.

## 3. Tokens and standards

- **ERC-20**: `transfer`, `transferFrom`, `approve`/`allowance`, **decimals** (don't assume 18), balances, `Transfer`/`Approval` events; the approve→transferFrom pattern and the risk of infinite approval.
- **ERC-721 / ERC-1155** (NFTs): ownership, `safeTransfer`, metadata/tokenURI, operator approvals.

## 4. Gas

- **Estimation** and limits; what happens on **out-of-gas** (it reverts, without leaving a half-done state); operations that scale with size (loops over unbounded arrays → gas DoS).
- **Gas reporting** to detect expensive functions.

## 5. Smart contract security

The most critical part (coordinate with an auditor for deep work):

- **Reentrancy**: an external call before updating the state allows re-entering and draining funds (checks-effects-interactions pattern, reentrancy guard).
- **Access control**: sensitive functions with `onlyOwner`/roles; a regular user must not be able to call them; ownership transfer.
- **Overflow/underflow** (mitigated in Solidity ≥0.8, but check unchecked blocks).
- **Front-running / MEV**: transactions that can be front-run (approve, auctions); commit-reveal where applicable.
- **Oracles**: manipulable prices (use TWAP, not spot); dependence on a single oracle.
- **delegatecall** and badly initialized **proxies**; predictable on-chain **randomness** (do not use `block.timestamp`/`blockhash` for draws).
- **DoS**: an account that blocks a queue, unbounded loops.

## 6. Upgradeability

- **Proxies** (UUPS, Transparent): the **storage layout** must not break between versions (do not reorder variables); the initializer cannot be called twice; only the right party can upgrade.

## 7. Signatures and permits

- **EIP-712** (typed signatures), **permit** (ERC-2612): a signature cannot be **reused** (replay) or used on another chain (chain id in the domain); signature expiration.

## 8. dApp ↔ contract integration

- The **wallet** (MetaMask): connecting, switching account and network, rejecting the signature; the dApp properly handles a **revert** (shows the error), a **pending** tx and the **confirmations**.
- **Reorg** (a confirmed tx that gets reverted), correct **nonce** and **chain id**; do not assume a sent tx is already mined.

## 9. Automate

- **Hardhat** or **Foundry**: unit tests, **fuzzing** (Foundry/echidna) and **invariants** (properties that must always hold, e.g. "the sum of balances = total supply"); **coverage** and **gas report**.
- **Static analysis**: Slither, Mythril (coordinate with `secure-code-analyst` for the SAST approach).
- The dApp (frontend) is tested with Playwright + a test wallet on a testnet.

## 10. Typical smart contract bugs

- **Reentrancy** that allows draining funds.
- Sensitive function without access control (anyone can call `withdraw`/`mint`).
- Assuming 18 decimals in a token that uses a different number.
- Operation that does not revert on an invalid precondition and leaves an inconsistent state.
- Reusable signature (no nonce/expiration/chain id) → replay.
- Proxy with a broken storage layout after an upgrade; initializer called twice.
- Price taken from an AMM spot price (manipulable) instead of a TWAP.
- Loop over a growing array → out-of-gas / DoS.

## 11. Typical questions for the team

When it is not written down, they are `MI-XX`:

- Which chain/network, and on which testnet or local node is it tested? Chain id?
- Do you have the source code, the ABI and the QA deployed addresses?
- Is the contract upgradeable (proxy)? Who can upgrade it?
- Which business invariants must always hold?
- Was there a security audit? What was left pending?
- Which token standards does it implement and with how many decimals?
