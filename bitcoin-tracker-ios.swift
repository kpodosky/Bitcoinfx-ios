// ContentView.swift
import SwiftUI

struct ContentView: View {
    @StateObject private var viewModel = BitcoinTrackerViewModel()
    
    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                // Header Section
                HeaderView(
                    percentage: viewModel.percentage,
                    priceChangeDirection: viewModel.priceChangeDirection,
                    priceChangePercentage: viewModel.priceChangePercentage
                )
                
                // Progress Bar
                ProgressBarView(percentage: viewModel.percentage)
                
                // Price Info
                PriceInfoView(
                    bitcoinPrice: viewModel.bitcoinPrice,
                    ethBtcRatio: viewModel.ethBtcRatio
                )
                
                Spacer()
            }
            .padding()
            .navigationTitle("Bitcoin Tracker")
            .onAppear {
                viewModel.startTracking()
            }
        }
    }
}

// HeaderView.swift
struct HeaderView: View {
    let percentage: Double
    let priceChangeDirection: String
    let priceChangePercentage: Double
    
    var headerText: String {
        percentage >= 25 ? "₿itcoin ∞ ↑" : "#bitcoin ↓"
    }
    
    var body: some View {
        VStack(spacing: 8) {
            Text("\(headerText) \(priceChangeDirection) \(formatPercentage(priceChangePercentage))")
                .font(.title2)
                .bold()
        }
    }
    
    private func formatPercentage(_ value: Double) -> String {
        let prefix = value >= 0 ? "+" : ""
        return "\(prefix)\(String(format: "%.2f", value))%"
    }
}

// ProgressBarView.swift
struct ProgressBarView: View {
    let percentage: Double
    
    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 0) {
                ForEach(0..<10, id: \.self) { index in
                    Rectangle()
                        .fill(getBlockColor(for: index))
                        .frame(height: 30)
                }
            }
            Text("\(Int(percentage))%")
                .font(.headline)
        }
    }
    
    private func getBlockColor(for index: Int) -> Color {
        let blockPercentage = Double(index + 1) * 10
        if percentage >= blockPercentage {
            return .black
        } else if blockPercentage == (percentage.rounded() / 10) * 10 {
            return .red
        }
        return .gray.opacity(0.3)
    }
}

// PriceInfoView.swift
struct PriceInfoView: View {
    let bitcoinPrice: Double
    let ethBtcRatio: Double
    
    var body: some View {
        HStack {
            Text("$\(String(format: "%.2f", bitcoinPrice))")
                .font(.title3)
                .bold()
            Spacer()
            Text("eth/btc: \(String(format: "%.2f", ethBtcRatio))")
                .font(.title3)
        }
        .padding(.top)
    }
}

// BitcoinTrackerViewModel.swift
class BitcoinTrackerViewModel: ObservableObject {
    private let BTC_ATH: Double = 100000
    private let REFRESH_INTERVAL: Double = 180
    
    @Published var bitcoinPrice: Double = 0
    @Published var previousBitcoinPrice: Double?
    @Published var ethBtcRatio: Double = 0
    @Published var percentage: Double = 0
    @Published var priceChangeDirection: String = "➡"
    @Published var priceChangePercentage: Double = 0
    
    private var timer: Timer?
    
    func startTracking() {
        updatePrices()
        timer = Timer.scheduledTimer(withTimeInterval: REFRESH_INTERVAL, repeats: true) { [weak self] _ in
            self?.updatePrices()
        }
    }
    
    private func updatePrices() {
        Task {
            await fetchBitcoinPrice()
            await fetchEthereumPrice()
            calculateMetrics()
        }
    }
    
    private func fetchBitcoinPrice() async {
        guard let url = URL(string: "https://mempool.space/api/v1/prices") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let response = try JSONDecoder().decode(BitcoinPriceResponse.self, from: data)
            
            await MainActor.run {
                let newPrice = response.USD
                if let previous = bitcoinPrice, previous > 0 {
                    let priceChange = newPrice - previous
                    priceChangePercentage = (priceChange / previous) * 100
                    priceChangeDirection = priceChange >= 0 ? "⇡" : "⇣"
                }
                bitcoinPrice = newPrice
                calculatePercentage()
            }
        } catch {
            print("Error fetching Bitcoin price: \(error)")
        }
    }
    
    private func fetchEthereumPrice() async {
        guard let url = URL(string: "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let response = try JSONDecoder().decode([CoinGeckoResponse].self, from: data)
            
            if let ethPrice = response.first(where: { $0.id == "ethereum" })?.current_price {
                await MainActor.run {
                    ethBtcRatio = ethPrice / bitcoinPrice
                }
            }
        } catch {
            print("Error fetching Ethereum price: \(error)")
        }
    }
    
    private func calculatePercentage() {
        percentage = (bitcoinPrice / BTC_ATH) * 100
    }
    
    private func calculateMetrics() {
        // Additional metrics calculations can be added here
    }
}

// API Response Models
struct BitcoinPriceResponse: Codable {
    let USD: Double
}

struct CoinGeckoResponse: Codable {
    let id: String
    let current_price: Double
    
    enum CodingKeys: String, CodingKey {
        case id
        case current_price = "current_price"
    }
}

// Preview Provider
struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
